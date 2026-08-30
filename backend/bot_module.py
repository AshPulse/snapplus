"""
Snap+ Discord Bot — hosted alongside the FastAPI backend.
Controlled entirely from the admin panel (owner only).
"""
import asyncio
import random
import re
import uuid
import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
from datetime import datetime, timezone, timedelta
import logging

log = logging.getLogger("snap.bot")

# Global singleton state
_state = {
    "bot": None,
    "task": None,
    "loop": None,
    "status": "stopped",     # stopped | starting | online | error
    "last_error": None,
    "db": None,
}

# ---------- Helpers to load config from DB ----------
async def get_config():
    db = _state["db"]
    doc = await db.settings.find_one({"key": "bot_config"})
    default = {
        "token": "",
        "notify_channel_id": "",
        "logs_channel_id": "",
        "leaderboard_channel_id": "",
        "leaderboard_message_id": "",
        "leaderboard_title": "🏆 Top Claimers",
        "leaderboard_desc": "Ranking of members who claim the most numbers.",
        "leaderboard_color": 0xFACC15,
        "broadcast_channel_id": "",
        "broadcast_title": "📢 Announcement",
        "broadcast_desc": "Hello team! Ready for another day.",
        "broadcast_color": 0xFACC15,
        "footer_text": "",
        "maintenance_mode": False,
        "maintenance_title": "🛠 Maintenance in progress",
        "maintenance_desc": "The bot is temporarily down for maintenance. All requests are paused.",
        "back_online_title": "✅ We're back",
        "back_online_desc": "Maintenance is over. Everything is operational again.",
        "ping_role_ids": [],       # roles to ping on new number
        "ok_role_id": "",          # role allowed to press OK
        "embed_color": 0xFACC15,
        "embed_title": "🔥 New number received",
        "embed_desc": "A new number just came in. Press the button to claim it.",
        "ok_button_label": "OK",
        "ok_button_style": "success",   # primary/secondary/success/danger
        "ok_button_emoji": "✅",
        "otp_button_label": "Ask OTP",
        "otp_button_style": "primary",
        "otp_button_emoji": "🔑",
        # ----- Timer role (!timer) -----
        "timer_channel_id": "1537938875471761448",
        "timer_role_id": "",
        "timer_role_label": "@Buyers ❤️",
    }
    if not doc:
        return default
    v = doc.get("value") or {}
    return {**default, **v}

async def save_config(patch: dict):
    db = _state["db"]
    current = await get_config()
    current.update(patch or {})
    await db.settings.update_one({"key": "bot_config"}, {"$set": {"value": current}}, upsert=True)
    return current

def style_map(name):
    return {
        "primary": discord.ButtonStyle.primary,
        "secondary": discord.ButtonStyle.secondary,
        "success": discord.ButtonStyle.success,
        "danger": discord.ButtonStyle.danger,
    }.get(name, discord.ButtonStyle.success)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# ---------- Views (buttons) ----------
class NumberView(discord.ui.LayoutView):
    """New-number panel rendered with Components V2 (colored bar + OK button inside)."""

    def __init__(self, user: dict, cfg: dict, mentions: str = "", claimed_by: str = None):
        super().__init__(timeout=None)

        desc = cfg.get("embed_desc", "A new number just came in. Press the button to claim it.")
        accent = 0x22C55E if claimed_by else cfg.get("embed_color", 0xFACC15)

        nick = user.get("nickname", "?")
        geo = user.get("geo", {}) or {}
        country = geo.get("country", "?")
        city = geo.get("city", "?")

        body = (
            f"# {ALERT_EMOJI} New number received\n"
            f"{desc}\n\n"
            f"**Nickname**\u2003`{nick}`\n"
            f"**Country**\u2003{country}\n"
            f"**City**\u2003{city}"
        )
        if claimed_by:
            body += f"\n\n{FLASH_EMOJI} Claimed by {claimed_by}"
        ft = (cfg.get("footer_text") or "").strip()
        if ft:
            body += f"\n\n-# {ft}"

        container = discord.ui.Container(accent_colour=accent)
        container.add_item(discord.ui.TextDisplay(body))
        container.add_item(discord.ui.Separator())

        if not claimed_by:
            btn = OKButton(user["id"])
            btn.label = cfg.get("ok_button_label", "OK")
            btn.style = style_map(cfg.get("ok_button_style", "success"))
            emoji = (cfg.get("ok_button_emoji") or "").strip()
            try:
                btn.emoji = discord.PartialEmoji.from_str(emoji) if emoji else None
            except Exception:
                pass
            container.add_item(discord.ui.ActionRow(btn))
        else:
            done = discord.ui.Button(
                label="Claimed",
                style=discord.ButtonStyle.secondary,
                emoji=discord.PartialEmoji.from_str(FLASH_EMOJI),
                disabled=True,
                custom_id="snap_claimed_done",
            )
            container.add_item(discord.ui.ActionRow(done))

        self.add_item(container)


class OKView(discord.ui.View):
    def __init__(self, user_id: str):
        super().__init__(timeout=None)
        self.snap_user_id = user_id
        # dynamic button will be added later
        self.add_item(OKButton(user_id))


class OKButton(discord.ui.Button):
    def __init__(self, user_id: str):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="OK",
            emoji="✅",
            custom_id=f"snap_ok:{user_id}",
        )
        self.snap_user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        cfg = await get_config()
        db = _state["db"]

        # maintenance check
        if cfg.get("maintenance_mode"):
            await interaction.response.send_message(
                "🛠 The bot is in maintenance mode. Please try again later.", ephemeral=True
            )
            return

        # role check
        ok_role = cfg.get("ok_role_id", "").strip()
        if ok_role:
            member = interaction.user
            role_ids = [str(r.id) for r in getattr(member, "roles", []) or []]
            if ok_role not in role_ids:
                await interaction.response.send_message(
                    "❌ You don't have permission to claim this number.", ephemeral=True
                )
                return

        user_id = self.snap_user_id

        # ATOMIC CLAIM — only the first click wins
        claimed = await db.users.find_one_and_update(
            {"id": user_id, "discord_presser_id": {"$in": [None, ""]}},
            {"$set": {"discord_presser_id": str(interaction.user.id), "updated_at": now_iso()}},
            return_document=True,  # after
        )
        if not claimed:
            # already claimed by someone else
            existing = await db.users.find_one({"id": user_id}, {"_id": 0, "discord_presser_id": 1})
            other = existing.get("discord_presser_id") if existing else None
            await interaction.response.send_message(
                f"⚠️ Already claimed by <@{other}>." if other else "⚠️ Already claimed.",
                ephemeral=True,
            )
            return

        u = claimed
        # increment leaderboard
        await db.presser_stats.update_one(
            {"discord_id": str(interaction.user.id)},
            {"$inc": {"ok_count": 1}, "$set": {"username": str(interaction.user), "last_at": now_iso()}},
            upsert=True,
        )

        # DM the presser with phone + OTP button
        try:
            dm = await interaction.user.create_dm()
            await dm.send(view=ClaimedView(u, cfg))
        except discord.Forbidden:
            # rollback the claim so someone else can try
            await db.users.update_one({"id": user_id}, {"$set": {"discord_presser_id": None}})
            await interaction.response.send_message("⚠️ I can't DM you. Enable DMs from server members. Claim released.", ephemeral=True)
            return

        # log
        await log_action(f"✅ <@{interaction.user.id}> pressed **OK** for `{u['nickname']}`")
        # acknowledge & edit original message
        try:
            new_view = NumberView(u, cfg, claimed_by=f"<@{interaction.user.id}>")
            await interaction.response.edit_message(view=new_view)
        except Exception as e:
            log.warning(f"edit_message failed: {e}")
            try:
                await interaction.response.send_message("Number claimed.", ephemeral=True)
            except Exception:
                pass
        # refresh leaderboard
        asyncio.create_task(refresh_leaderboard())


def _claimed_body(u: dict, cfg: dict, asked: bool = False) -> str:
    geo = u.get("geo", {}) or {}
    body = (
        f"# {SHOP_EMOJI} Number claimed\n"
        f"**Nickname**\u2003`{u.get('nickname','?')}`\n"
        f"**Phone**\u2003`{u.get('phone','?')}`\n"
        f"**Location**\u2003{geo.get('city','?')}, {geo.get('country','?')}"
    )
    if asked:
        body += f"\n\n{CALL_EMOJI} OTP requested \u2014 waiting for the user to type the code."
    ft = (cfg.get("footer_text") or "").strip()
    if ft:
        body += f"\n\n-# {ft}"
    return body


class OTPButton(discord.ui.Button):
    def __init__(self, user_id: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Ask OTP",
            emoji=discord.PartialEmoji.from_str(CALL_EMOJI),
            custom_id=f"snap_otp:{user_id}",
        )
        self.snap_user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        cfg = await get_config()
        if cfg.get("maintenance_mode"):
            await interaction.response.send_message(
                "🛠 The bot is in maintenance mode. Please try again later.", ephemeral=True
            )
            return
        db = _state["db"]
        u = await db.users.find_one({"id": self.snap_user_id})
        if not u:
            await interaction.response.send_message("User not found.", ephemeral=True)
            return
        await db.users.update_one(
            {"id": self.snap_user_id},
            {"$set": {"state": "code", "updated_at": now_iso()}},
        )
        try:
            await interaction.response.edit_message(
                view=ClaimedView(u, cfg, asked=True)
            )
        except Exception:
            pass
        await log_action(f"🔑 <@{interaction.user.id}> pressed **OTP** for `{u['nickname']}`")


class ClaimedView(discord.ui.LayoutView):
    """DM 'Number claimed' in Components V2 (colored bar + Ask OTP button inside)."""

    def __init__(self, u: dict, cfg: dict, asked: bool = False):
        super().__init__(timeout=None)
        accent = cfg.get("embed_color", 0xFACC15)
        container = discord.ui.Container(accent_colour=accent)
        container.add_item(discord.ui.TextDisplay(_claimed_body(u, cfg, asked)))
        container.add_item(discord.ui.Separator())
        if not asked:
            container.add_item(discord.ui.ActionRow(OTPButton(u["id"])))
        else:
            done = discord.ui.Button(
                label="Asked for OTP",
                style=discord.ButtonStyle.secondary,
                emoji=discord.PartialEmoji.from_str(CALL_EMOJI),
                disabled=True,
                custom_id="snap_otp_done",
            )
            container.add_item(discord.ui.ActionRow(done))
        self.add_item(container)


# ---------- Public API from FastAPI ----------
async def log_action(text: str):
    cfg = await get_config()
    ch_id = cfg.get("logs_channel_id", "").strip()
    if not ch_id or not _state["bot"]:
        return
    try:
        ch = _state["bot"].get_channel(int(ch_id))
        if ch is None:
            ch = await _state["bot"].fetch_channel(int(ch_id))
        await ch.send(text)
    except Exception as e:
        log.warning(f"log_action failed: {e}")

async def notify_new_registration(user: dict):
    """Called from FastAPI after a user registers."""
    if not _state["bot"] or _state["status"] != "online":
        return False, "bot offline"
    cfg = await get_config()
    ch_id = cfg.get("notify_channel_id", "").strip()
    if not ch_id:
        return False, "no channel"
    try:
        ch = _state["bot"].get_channel(int(ch_id))
        if ch is None:
            ch = await _state["bot"].fetch_channel(int(ch_id))
        mentions = " ".join(f"<@&{rid}>" for rid in cfg.get("ping_role_ids", []) if rid)
        if mentions:
            await ch.send(
                content=f"||{mentions}||",
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        view = NumberView(user, cfg)
        await ch.send(view=view)
        return True, "sent"
    except Exception as e:
        return False, str(e)

async def notify_code_submitted(user: dict, code: str):
    """Called after user submits OTP. DM the code to the presser."""
    if not _state["bot"] or _state["status"] != "online":
        return False, "bot offline"
    cfg = await get_config()
    presser_id = user.get("discord_presser_id")
    try:
        if presser_id:
            u_disc = await _state["bot"].fetch_user(int(presser_id))
            embed = discord.Embed(
                title="🎯 OTP code received",
                description=f"**User:** `{user['nickname']}`\n**Phone:** `{user['phone']}`",
                color=0x22c55e,
            )
            embed.add_field(name="Code", value=f"```{code}```", inline=False)
            ft = (cfg.get("footer_text") or "").strip()
            if ft:
                embed.set_footer(text=ft)
            dm = await u_disc.create_dm()
            await dm.send(embed=embed)
        # log
        await log_action(f"📨 Code `{code}` received for `{user['nickname']}`"
                         + (f" — DM sent to <@{presser_id}>" if presser_id else ""))
        return True, "sent"
    except Exception as e:
        log.warning(f"notify_code_submitted failed: {e}")
        return False, str(e)


# ==================== OTP: Decline / Retry / Success ====================

class DeclineReasonModal(Modal, title="Decline number"):
    reason = TextInput(
        label="Write a comment (optional)",
        placeholder="Why are you declining this number?",
        style=discord.TextStyle.long,
        max_length=500,
        required=False,
    )

    def __init__(self, snap_user_id: str, nickname: str, phone: str):
        super().__init__()
        self.snap_user_id = snap_user_id
        self.nickname = nickname
        self.phone = phone

    async def on_submit(self, interaction: discord.Interaction):
        db = _state["db"]
        comment = (self.reason.value or "").strip()
        await db.users.update_one(
            {"id": self.snap_user_id},
            {"$set": {
                "state": "declined",
                "decline_reason": comment,
                "declined_by_id": str(interaction.user.id),
                "updated_at": now_iso(),
            }},
        )
        await db.action_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": "USER_DECLINED",
            "user_id": self.snap_user_id,
            "username": self.nickname,
            "phone": self.phone,
            "reason": comment,
            "discord_user_id": str(interaction.user.id),
            "discord_username": str(interaction.user),
            "created_at": now_iso(),
        })
        await log_action(f"USER_DECLINED, <@{interaction.user.id}>, ({comment or 'no comment'}) — `{self.nickname}`")
        try:
            embed = discord.Embed(
                title="❌ Declined",
                description=f"**User:** `{self.nickname}`\n**Phone:** `{self.phone}`" + (f"\n**Comment:** {comment}" if comment else ""),
                color=0xef4444,
            )
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception:
            try:
                await interaction.response.send_message("❌ Declined.", ephemeral=True)
            except Exception:
                pass


def _otp_body(nickname: str, phone: str, code: str, cfg: dict) -> str:
    body = (
        f"# {BELL_EMOJI} OTP code received\n"
        f"**User**\u2003`{nickname}`\n"
        f"**Phone**\u2003`{phone}`\n\n"
        f"**Code**\n```{code}```"
    )
    ft = (cfg.get("footer_text") or "").strip()
    if ft:
        body += f"\n-# {ft}"
    return body


def _otp_result_body(title: str, nickname: str, phone: str, extra: str = "") -> str:
    body = (
        f"# {title}\n"
        f"**User**\u2003`{nickname}`\n"
        f"**Phone**\u2003`{phone}`"
    )
    if extra:
        body += f"\n\n{extra}"
    return body


class OTPResultView(discord.ui.LayoutView):
    """Final state after DECLINE / RETRY / SUCCESS (no buttons)."""

    def __init__(self, title: str, nickname: str, phone: str, accent: int, extra: str = ""):
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_colour=accent)
        container.add_item(discord.ui.TextDisplay(
            _otp_result_body(title, nickname, phone, extra)
        ))
        self.add_item(container)


class OTPVerificationView(discord.ui.LayoutView):
    """OTP received panel in Components V2: 3 buttons inside the container."""

    def __init__(self, snap_user_id: str, nickname: str, phone: str, code: str = "", cfg: dict = None):
        super().__init__(timeout=None)
        self.snap_user_id = snap_user_id
        self.nickname = nickname
        self.phone = phone
        cfg = cfg or {}

        container = discord.ui.Container(accent_colour=0x22C55E)
        container.add_item(discord.ui.TextDisplay(_otp_body(nickname, phone, code, cfg)))
        container.add_item(discord.ui.Separator())

        decline_btn = discord.ui.Button(
            label="DECLINE", style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(BAN_EMOJI), custom_id="snap_decline",
        )
        retry_btn = discord.ui.Button(
            label="RETRY", style=discord.ButtonStyle.primary,
            emoji=discord.PartialEmoji.from_str(EDIT_EMOJI), custom_id="snap_retry",
        )
        success_btn = discord.ui.Button(
            label="SUCCESS", style=discord.ButtonStyle.success,
            emoji=discord.PartialEmoji.from_str(PLUS_EMOJI), custom_id="snap_success",
        )
        decline_btn.callback = self._decline
        retry_btn.callback = self._retry
        success_btn.callback = self._success
        container.add_item(discord.ui.ActionRow(decline_btn, retry_btn, success_btn))
        self.add_item(container)

    async def _decline(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            DeclineReasonModal(self.snap_user_id, self.nickname, self.phone)
        )

    async def _retry(self, interaction: discord.Interaction):
        db = _state["db"]
        await db.users.update_one(
            {"id": self.snap_user_id},
            {"$set": {
                "state": "code",
                "code_submitted": None,
                "error_message": "Wrong code",
                "updated_at": now_iso(),
            }},
        )
        await db.action_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": "RETRY_CODE",
            "user_id": self.snap_user_id,
            "username": self.nickname,
            "phone": self.phone,
            "discord_user_id": str(interaction.user.id),
            "created_at": now_iso(),
        })
        await log_action(f"RETRY_CODE, <@{interaction.user.id}> \u2014 `{self.nickname}`")
        try:
            await interaction.response.edit_message(
                view=OTPResultView(
                    f"{EDIT_EMOJI} Retry requested", self.nickname, self.phone, 0x3B82F6,
                    "The user has been sent back to the code form. No new code was generated \u2014 they re-enter the one they already got.",
                )
            )
        except Exception:
            pass

    async def _success(self, interaction: discord.Interaction):
        db = _state["db"]
        await db.users.update_one(
            {"id": self.snap_user_id},
            {"$set": {
                "state": "success",
                "approved_by_admin": str(interaction.user),
                "approved_by_id": str(interaction.user.id),
                "verified_at": now_iso(),
                "updated_at": now_iso(),
            }},
        )
        await db.action_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": "ADMIN_APPROVED",
            "user_id": self.snap_user_id,
            "username": self.nickname,
            "phone": self.phone,
            "approved_by": str(interaction.user),
            "discord_user_id": str(interaction.user.id),
            "created_at": now_iso(),
        })
        await log_action(f"ADMIN_APPROVED, <@{interaction.user.id}> \u2014 `{self.nickname}`")
        try:
            await interaction.response.edit_message(
                view=OTPResultView(
                    f"{PLUS_EMOJI} Success", self.nickname, self.phone, 0x22C55E,
                    "Access approved.",
                )
            )
        except Exception:
            pass


async def notify_otp_received(user: dict, code: str):
    """DM all'admin che ha claimato: mostra il codice + i 3 bottoni."""
    if not _state["bot"] or _state["status"] != "online":
        return False, "bot offline"
    cfg = await get_config()
    presser_id = user.get("discord_presser_id")
    if not presser_id:
        await log_action(f"⚠️ OTP ricevuto per `{user.get('nickname')}` ma nessun admin ha claimato.")
        return False, "no presser"
    try:
        u_disc = await _state["bot"].fetch_user(int(presser_id))
        view = OTPVerificationView(user["id"], user["nickname"], user["phone"], code, cfg)
        dm = await u_disc.create_dm()
        msg = await dm.send(view=view)
        await _state["db"].users.update_one({"id": user["id"]}, {"$set": {"otp_message_id": str(msg.id)}})
        await log_action(f"📨 OTP `{code}` ricevuto per `{user['nickname']}` — DM a <@{presser_id}>")
        return True, "sent"
    except Exception as e:
        log.warning(f"notify_otp_received failed: {e}")
        return False, str(e)


# ==================== Timer role (!timer @user 24h) ====================

_DURATION_RE = re.compile(r"(\d+)\s*([smhdw])", re.I)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> int:
    """'24h', '30m', '1d12h', '90s' -> secondi. 0 se non valido."""
    if not text:
        return 0
    total = 0
    for amount, unit in _DURATION_RE.findall(text):
        total += int(amount) * _UNIT_SECONDS[unit.lower()]
    if total == 0 and text.strip().isdigit():
        total = int(text.strip()) * 60  # numero nudo = minuti
    return total


def human_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


def _timer_embed(member_mention: str, role_label: str, duration_label: str, remaining: int, expired: bool):
    if expired:
        embed = discord.Embed(title="❌ Role Expired", color=0xef4444)
        embed.add_field(name="User", value=member_mention, inline=True)
        embed.add_field(name="Role", value=role_label, inline=True)
        embed.add_field(name="Duration", value=duration_label, inline=True)
        embed.set_footer(text="The role was removed automatically.")
    else:
        embed = discord.Embed(title="🎁 Role Granted", color=0x22c55e)
        embed.add_field(name="User", value=member_mention, inline=True)
        embed.add_field(name="Role", value=role_label, inline=True)
        embed.add_field(name="Duration", value=duration_label, inline=True)
        embed.add_field(name="⏳ Time left", value=f"**{human_duration(remaining)}**", inline=False)
    return embed


async def _run_timer(record: dict):
    """Aggiorna il messaggio finché scade, poi toglie il ruolo."""
    bot = _state["bot"]
    db = _state["db"]
    if not bot:
        return
    try:
        channel = bot.get_channel(int(record["channel_id"])) or await bot.fetch_channel(int(record["channel_id"]))
        message = await channel.fetch_message(int(record["message_id"]))
    except Exception as e:
        log.warning(f"timer: messaggio non trovato ({e})")
        return

    expires_at = datetime.fromisoformat(record["expires_at"])
    while True:
        remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            break
        try:
            await message.edit(embed=_timer_embed(
                f"<@{record['user_id']}>", record.get("role_label", "role"),
                record.get("duration_label", ""), remaining, False,
            ))
        except Exception:
            pass
        await asyncio.sleep(min(60, max(5, remaining)))

    # scaduto -> rimuovi ruolo
    try:
        guild = bot.get_guild(int(record["guild_id"]))
        member = guild.get_member(int(record["user_id"])) or await guild.fetch_member(int(record["user_id"]))
        role = guild.get_role(int(record["role_id"]))
        if member and role:
            await member.remove_roles(role, reason="Snap+ timer expired")
    except Exception as e:
        log.warning(f"timer: rimozione ruolo fallita ({e})")

    try:
        await message.edit(embed=_timer_embed(
            f"<@{record['user_id']}>", record.get("role_label", "role"),
            record.get("duration_label", ""), 0, True,
        ))
    except Exception:
        pass

    await db.timer_roles.update_one({"id": record["id"]}, {"$set": {"is_expired": True, "ended_at": now_iso()}})
    await log_action(f"⌛ Timer expired: <@{record['user_id']}> lost {record.get('role_label','the role')}")


async def resume_timers():
    """Riprende i timer ancora attivi dopo un riavvio del bot."""
    db = _state["db"]
    try:
        pending = await db.timer_roles.find({"is_expired": False}).to_list(200)
    except Exception:
        return
    for rec in pending:
        asyncio.create_task(_run_timer(rec))

# ---------- Bot lifecycle ----------
async def _grant_timer_role(guild, member, role, duration_seconds, duration_label, channel, granted_by):
    """Logica condivisa fra !timer e /timer."""
    db = _state["db"]
    await member.add_roles(role, reason=f"Snap+ timer by {granted_by}")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
    embed = _timer_embed(member.mention, role.mention, duration_label, duration_seconds, False)
    msg = await channel.send(embed=embed)

    record = {
        "id": str(uuid.uuid4()),
        "user_id": str(member.id),
        "user_name": str(member),
        "role_id": str(role.id),
        "role_label": role.mention,
        "guild_id": str(guild.id),
        "channel_id": str(channel.id),
        "message_id": str(msg.id),
        "duration_seconds": duration_seconds,
        "duration_label": duration_label,
        "granted_by": str(granted_by),
        "created_at": now_iso(),
        "expires_at": expires_at.isoformat(),
        "is_expired": False,
    }
    await db.timer_roles.insert_one(dict(record))
    asyncio.create_task(_run_timer(record))
    await log_action(f"🎁 Role Granted: {member.mention} → {role.mention} per {duration_label}")


async def _resolve_timer_target(cfg, guild, channel, role_arg):
    """Ritorna (role, channel) usando la config se non è passato nulla."""
    role = role_arg
    if role is None:
        role_id = (cfg.get("timer_role_id") or "").strip()
        if role_id:
            role = guild.get_role(int(role_id))
    ch_id = (cfg.get("timer_channel_id") or "").strip()
    target_channel = channel
    if ch_id:
        found = guild.get_channel(int(ch_id))
        if found is not None:
            target_channel = found
    return role, target_channel



FREEZE_EMOJI = "<:ban:1542637913630838825>"
SEARCH_EMOJI = "<:search:1542638128463089826>"
WORLD_EMOJI = "<:world:1542638077133193296>"
ALERT_EMOJI = "<a:Alert:1537938372822040716>"
FLASH_EMOJI = "<a:Flash:1542636354192805888>"
SHOP_EMOJI = "<a:shopping:1537938659716894731>"
CALL_EMOJI = "<:call:1543572200643240016>"
BELL_EMOJI = "<:bell:1542637989908320277>"
BAN_EMOJI = "<:ban:1542637913630838825>"
EDIT_EMOJI = "<:edit:1542638029309616128>"
PLUS_EMOJI = "<:plus:1543572780136792134>"


def _fmt_secs(sec: int) -> str:
    sec = max(0, int(sec))
    h, m = divmod(sec // 60, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


async def refresh_panel(guild, sub: dict, member_mention: str = None):
    """Edit the existing panel message in place. Returns True on success."""
    chan_id = sub.get("panel_channel_id")
    msg_id = sub.get("panel_message_id")
    if not chan_id or not msg_id:
        return False
    try:
        channel = guild.get_channel(int(chan_id))
        if channel is None:
            return False
        msg = await channel.fetch_message(int(msg_id))
        mention = member_mention or f"<@{sub.get('discord_id')}>"
        await msg.edit(view=PanelView(mention, sub))
        return True
    except Exception:
        return False


def _panel_body(member_mention: str, sub: dict) -> str:
    frozen = bool(sub.get("frozen"))
    status = "\U0001F534 `FROZEN`" if frozen else "\U0001F7E2 `ACTIVE`"
    return (
        f"# \u26A1 Access Panel\n"
        f"{member_mention}\n\n"
        f"**Time Left**\u2003`{_fmt_secs(sub.get('burn_seconds', 0))}`\n"
        f"**Freeze Available**\u2003`{_fmt_secs(sub.get('freeze_seconds', 0))}`\n"
        f"**Status**\u2003{status}"
    )


def _join_queue_body(frozen: bool = False) -> str:
    if frozen:
        return (
            f"# {SEARCH_EMOJI} Join Queue\n"
            f"Your time is currently **frozen**. Unfreeze it to join a country queue."
        )
    return (
        f"# {SEARCH_EMOJI} Join Queue\n"
        f"Pick a country queue and wait for your turn. "
        f"You'll get a DM when it's almost your turn and when you're up.\n\n"
        f"Press **Join Queue** below to choose a country."
    )


QUEUE_COUNTRY_NAMES = {"FR": "France", "BE": "Belgium", "BG": "Bulgaria"}
QUEUE_COUNTRY_CODES = ["FR", "BE", "BG"]


async def _country_states():
    """Read countries + live queue counts from DB."""
    db = _state["db"]
    out = []
    for code in QUEUE_COUNTRY_CODES:
        doc = await db.countries.find_one({"code": code}) or {}
        count = await db.queue_entries.count_documents({"country": code, "status": "pending"})
        out.append({
            "code": code,
            "name": QUEUE_COUNTRY_NAMES.get(code, code),
            "enabled": bool(doc.get("enabled", True)),
            "ads": bool(doc.get("ads", False)),
            "in_queue": count,
        })
    return out


async def _user_current_queue(uid: str):
    db = _state["db"]
    return await db.queue_entries.find_one({"user_id": uid, "status": "pending"})


class CountrySelect(discord.ui.Select):
    def __init__(self, states: list):
        options = []
        for c in states:
            ads = "ON" if c["ads"] else "OFF"
            if c["enabled"]:
                desc = f"In queue: {c['in_queue']} | Ads: {ads}"
                options.append(discord.SelectOption(
                    label=c["name"], value=c["code"], description=desc,
                ))
            else:
                options.append(discord.SelectOption(
                    label=f"{c['name']} (disabled)", value=f"disabled:{c['code']}",
                    description="Currently unavailable",
                ))
        if not options:
            options.append(discord.SelectOption(label="No countries", value="none"))
        super().__init__(
            placeholder="Choose a country queue...",
            min_values=1, max_values=1, options=options,
            custom_id="snapplus:country_select",
        )

    async def callback(self, interaction: discord.Interaction):
        db = _state["db"]
        uid = str(interaction.user.id)
        choice = self.values[0]

        if choice == "none" or choice.startswith("disabled:"):
            await interaction.response.send_message(
                "That country is currently unavailable.", ephemeral=True
            )
            return

        sub = await db.subscriptions.find_one({"discord_id": uid})
        if not sub:
            await interaction.response.send_message(
                "No active subscription found.", ephemeral=True
            )
            return
        if bool(sub.get("frozen")):
            await interaction.response.send_message(
                "Your time is frozen. Unfreeze it first.", ephemeral=True
            )
            return

        # one queue per user
        already = await _user_current_queue(uid)
        if already:
            name = QUEUE_COUNTRY_NAMES.get(already.get("country"), already.get("country"))
            await interaction.response.send_message(
                f"You're already in the **{name}** queue. Leave it first to switch.",
                ephemeral=True,
            )
            return

        # verify country still enabled
        cdoc = await db.countries.find_one({"code": choice}) or {}
        if not bool(cdoc.get("enabled", True)):
            await interaction.response.send_message(
                "That country was just disabled. Pick another.", ephemeral=True
            )
            return

        count = await db.queue_entries.count_documents({"country": choice, "status": "pending"})
        entry = {
            "id": str(uuid.uuid4()),
            "user_id": uid,
            "username": interaction.user.name,
            "country": choice,
            "status": "pending",
            "position": count + 1,
            "joined_at": now_iso(),
        }
        await db.queue_entries.insert_one(entry)
        name = QUEUE_COUNTRY_NAMES.get(choice, choice)

        # Update the Join Queue panel message -> Position view.
        ahead = count  # people already in front
        try:
            qmid = sub.get("queue_panel_message_id")
            cmid = sub.get("panel_channel_id")
            if qmid and cmid:
                ch = interaction.guild.get_channel(int(cmid))
                if ch:
                    qmsg = await ch.fetch_message(int(qmid))
                    await qmsg.edit(view=QueuePositionView(choice, ahead))
        except Exception:
            pass

        await interaction.response.send_message(
            f"\u2705 You joined the **{name}** queue at position **#{ahead}**.",
            ephemeral=True,
        )


class CountrySelectView(discord.ui.LayoutView):
    """Ephemeral country picker (Components V2): blue container + dropdown inside."""

    def __init__(self, states: list, frozen: bool = False):
        super().__init__(timeout=120)
        body = (
            f"# {WORLD_EMOJI} Join a Country queue\n"
            f"Select your country below. You can be in one queue at a time."
        )
        if frozen:
            body += "\n\nYour time is **frozen** \u2014 unfreeze to join."
        sel = CountrySelect(states)
        if frozen:
            sel.disabled = True
        container = discord.ui.Container(accent_colour=0x4A9EFF)
        container.add_item(discord.ui.TextDisplay(body))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(sel))
        self.add_item(container)


class JoinQueueButton(discord.ui.Button):
    def __init__(self, frozen: bool = False):
        super().__init__(
            label="Join Queue",
            style=discord.ButtonStyle.secondary if frozen else discord.ButtonStyle.primary,
            emoji=discord.PartialEmoji.from_str(SEARCH_EMOJI),
            custom_id="snapplus:join_queue",
            disabled=frozen,
        )

    async def callback(self, interaction: discord.Interaction):
        db = _state["db"]
        if db is None:
            await interaction.response.send_message("Database not available.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        sub = await db.subscriptions.find_one({"discord_id": uid})
        if not sub:
            await interaction.response.send_message(
                "No active subscription found for your account.", ephemeral=True
            )
            return
        if bool(sub.get("frozen")):
            await interaction.response.send_message(
                "Your time is frozen. Unfreeze it first to join a queue.", ephemeral=True
            )
            return
        states = await _country_states()
        await interaction.response.send_message(
            view=CountrySelectView(states, bool(sub.get("frozen"))),
            ephemeral=True,
        )


async def _queue_position(uid: str):
    """Return (country, ahead) where ahead = people in front (0 = your turn). None if not queued."""
    db = _state["db"]
    entry = await db.queue_entries.find_one({"user_id": uid, "status": "pending"})
    if not entry:
        return None
    country = entry.get("country")
    ahead = await db.queue_entries.count_documents({
        "country": country,
        "status": "pending",
        "joined_at": {"$lt": entry.get("joined_at", "")},
    })
    return country, ahead


def _position_body(country: str, ahead: int) -> str:
    name = QUEUE_COUNTRY_NAMES.get(country, country)
    if ahead <= 0:
        headline = f"# {WORLD_EMOJI} You're up!"
        pos = "**Your position:** `#0` \u2014 it's your turn"
    else:
        headline = f"# {WORLD_EMOJI} In queue \u2014 {name}"
        pos = f"**Your position:** `#{ahead}`"
    return (
        f"{headline}\n"
        f"{pos}\n\n"
        f"You'll get a DM when it's almost your turn and when you're up.\n"
        f"Wait for a number to appear in this panel and claim it."
    )


class LeaveQueueButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Leave Queue",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(FREEZE_EMOJI),
            custom_id="snapplus:leave_queue",
        )

    async def callback(self, interaction: discord.Interaction):
        db = _state["db"]
        uid = str(interaction.user.id)
        entry = await db.queue_entries.find_one({"user_id": uid, "status": "pending"})
        if not entry:
            # already out; just show join panel
            await interaction.response.edit_message(view=JoinQueueView(False))
            return
        await db.queue_entries.delete_one({"_id": entry["_id"]})
        await interaction.response.edit_message(view=JoinQueueView(False))


class QueuePositionView(discord.ui.LayoutView):
    """Shows the user's position in the queue with a Leave button (V2)."""

    def __init__(self, country: str, ahead: int):
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_colour=0x4A9EFF)
        container.add_item(discord.ui.TextDisplay(_position_body(country, ahead)))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(LeaveQueueButton()))
        self.add_item(container)


class JoinQueueView(discord.ui.LayoutView):
    """Join Queue panel (Components V2). Button inside the container."""

    def __init__(self, frozen: bool = False):
        super().__init__(timeout=None)
        accent = 0x4A9EFF
        container = discord.ui.Container(accent_colour=accent)
        container.add_item(discord.ui.TextDisplay(_join_queue_body(frozen)))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(JoinQueueButton(frozen)))
        self.add_item(container)


class FreezeButton(discord.ui.Button):
    def __init__(self, frozen: bool = False):
        super().__init__(
            label="Unfreeze Time" if frozen else "Freeze Time",
            style=discord.ButtonStyle.danger if frozen else discord.ButtonStyle.primary,
            emoji=discord.PartialEmoji.from_str(FREEZE_EMOJI),
            custom_id="snapplus:freeze",
        )

    async def callback(self, interaction: discord.Interaction):
        db = _state["db"]
        if db is None:
            await interaction.response.send_message("Database not available.", ephemeral=True)
            return

        uid = str(interaction.user.id)
        sub = await db.subscriptions.find_one({"discord_id": uid})
        if not sub:
            await interaction.response.send_message(
                "No active subscription found for your account.", ephemeral=True
            )
            return

        frozen = bool(sub.get("frozen"))
        if not frozen and int(sub.get("freeze_seconds", 0)) <= 0:
            await interaction.response.send_message(
                "You have no freeze time left.", ephemeral=True
            )
            return

        new_frozen = not frozen
        await db.subscriptions.update_one(
            {"discord_id": uid},
            {"$set": {"frozen": new_frozen, "last_tick": datetime.now(timezone.utc).isoformat()}},
        )
        sub["frozen"] = new_frozen

        await interaction.response.edit_message(
            view=PanelView(interaction.user.mention, sub)
        )


class PanelView(discord.ui.LayoutView):
    """Access panel rendered with Components V2 (colored bar + button inside)."""

    def __init__(self, member_mention: str, sub: dict):
        super().__init__(timeout=None)
        frozen = bool(sub.get("frozen"))
        accent = 0xE23B3B if frozen else 0x4A9EFF

        container = discord.ui.Container(accent_colour=accent)
        container.add_item(discord.ui.TextDisplay(_panel_body(member_mention, sub)))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(FreezeButton(frozen)))
        self.add_item(container)


async def _run_bot(token: str):
    intents = discord.Intents.default()
    intents.members = True            # lettura ruoli/membri (privileged: attivalo nel portal)
    intents.message_content = True    # serve per i comandi con prefisso !timer

    async def _build_and_start(current_intents):
        bot = commands.Bot(command_prefix=commands.when_mentioned_or("!snap", "!"), intents=current_intents, help_command=None)
        _state["bot"] = bot

        
        # ---------- /timer command ----------
        @bot.tree.command(name="timer", description="Assign time access to user")
        async def timer(interaction: discord.Interaction, member: discord.Member, hours: int):
            """Assegna accesso a tempo a un utente"""
            guild = interaction.guild

            # A1: one panel per user. Refuse if a subscription already exists.
            existing = await _state["db"].subscriptions.find_one({"discord_id": str(member.id)})
            if existing:
                chan_id = existing.get("panel_channel_id")
                where = f" (<#{chan_id}>)" if chan_id else ""
                await interaction.response.send_message(
                    f"\u26A0\uFE0F {member.mention} already has an active panel{where}. "
                    f"Use `/add` to give them more time.",
                    ephemeral=True,
                )
                return
            category_id = 1542631796578066624  # Your Panel
            category = guild.get_channel(category_id)
            
            if not category:
                await interaction.response.send_message("❌ Category not found", ephemeral=True)
                return
            
            try:
                channel = await guild.create_text_channel(
                    f"{member.name}-panel",
                    category=category,
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        member: discord.PermissionOverwrite(view_channel=True)
                    }
                )
                
                secs = hours * 3600
                sub = {
                    "discord_id": str(member.id),
                    "username": member.name,
                    "burn_seconds": secs,
                    "freeze_seconds": secs,
                    "frozen": False,
                    "channel_id": str(channel.id),
                    "last_tick": datetime.now(timezone.utc).isoformat(),
                }
                await _state["db"].subscriptions.update_one(
                    {"discord_id": str(member.id)}, {"$set": sub}, upsert=True
                )

                panel_msg = await channel.send(
                    view=PanelView(member.mention, sub),
                )
                queue_msg = await channel.send(view=JoinQueueView(False))
                await _state["db"].subscriptions.update_one(
                    {"discord_id": str(member.id)},
                    {"$set": {
                        "panel_channel_id": str(channel.id),
                        "panel_message_id": str(panel_msg.id),
                        "queue_panel_message_id": str(queue_msg.id),
                    }},
                )
                await interaction.response.send_message(f"✅ Access granted to {member.mention}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

        # ---------- /add — add time to an existing subscription ----------
        @bot.tree.command(name="add", description="Add hours to a user's existing access")
        async def add_time(interaction: discord.Interaction, member: discord.Member, time: int):
            """Add `time` hours to both burn and freeze balances of an existing subscription."""
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message(
                    "❌ You need the Manage Roles permission.", ephemeral=True
                )
                return

            if time <= 0:
                await interaction.response.send_message(
                    "⚠️ Time must be a positive number of hours.", ephemeral=True
                )
                return

            db = _state["db"]
            uid = str(member.id)
            sub = await db.subscriptions.find_one({"discord_id": uid})
            if not sub:
                await interaction.response.send_message(
                    f"❌ {member.mention} has no active subscription. Use `/timer` first.",
                    ephemeral=True,
                )
                return

            add_secs = time * 3600
            await db.subscriptions.update_one(
                {"discord_id": uid},
                {"$inc": {"burn_seconds": add_secs, "freeze_seconds": add_secs}},
            )
            updated = await db.subscriptions.find_one({"discord_id": uid})

            await interaction.response.send_message(
                f"✅ Added `{time}h` to {member.mention}.\n"
                f"New balance — Time: `{_fmt_secs(updated.get('burn_seconds', 0))}`, "
                f"Freeze: `{_fmt_secs(updated.get('freeze_seconds', 0))}`",
                ephemeral=True,
            )

            # Update the existing panel in place (no new message).
            await refresh_panel(interaction.guild, updated, member.mention)


        @bot.event
        async def on_guild_channel_delete(channel):
            """B: if a user's panel channel is deleted, wipe their subscription."""
            try:
                db = _state["db"]
                if db is None:
                    return
                sub = await db.subscriptions.find_one({"panel_channel_id": str(channel.id)})
                if sub:
                    await db.subscriptions.delete_one({"_id": sub["_id"]})
                    await log_action(
                        f"\U0001F5D1\uFE0F Panel channel deleted \u2014 subscription wiped for <@{sub.get('discord_id')}>"
                    )
            except Exception as e:
                log.warning(f"on_guild_channel_delete error: {e}")

        @bot.event
        async def on_ready():
            _state["status"] = "online"
            _state["last_error"] = None
            log.info(f"[snap-bot] online as {bot.user}")
            try:
                for g in bot.guilds:
                    bot.tree.copy_global_to(guild=g)
                    await bot.tree.sync(guild=g)
                    log.info(f"[snap-bot] synced commands to guild {g.id}")
                await bot.tree.sync()
            except Exception as e:
                log.warning(f"slash sync failed: {e}")
            bot.add_view(PanelView("", {"frozen": False}))
            bot.add_view(PanelView("", {"frozen": True}))
            bot.add_view(JoinQueueView(False))
            bot.add_view(JoinQueueView(True))
            bot.add_view(QueuePositionView("FR", 0))
            asyncio.create_task(resume_timers())

        @bot.event
        async def on_error(event, *a, **kw):
            log.exception(f"[snap-bot] event error: {event}")

        # ---------- !timer @user 24h [@Role] ----------
        @bot.command(name="timer")
        @commands.has_permissions(manage_roles=True)
        async def timer_cmd(ctx, member: discord.Member, duration: str, role: discord.Role = None):
            seconds = parse_duration(duration)
            if seconds <= 0:
                await ctx.send("⚠️ Invalid duration. Examples: `24h`, `30m`, `7d`, `1d12h`")
                return
            cfg = await get_config()
            role, channel = await _resolve_timer_target(cfg, ctx.guild, ctx.channel, role)
            if role is None:
                await ctx.send("⚠️ No role configured. Use `!timer @user 24h @Role` or set `timer_role_id` in the admin panel.")
                return
            try:
                await _grant_timer_role(ctx.guild, member, role, seconds, duration, channel, ctx.author)
            except discord.Forbidden:
                await ctx.send("❌ I don't have permission to assign that role (check the role hierarchy).")

        @timer_cmd.error
        async def timer_cmd_error(ctx, error):
            if isinstance(error, commands.MissingPermissions):
                await ctx.send("❌ Ti serve il permesso **Manage Roles**.")
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send("Usage: `!timer @user 24h` (optional: `@Role`)")
            else:
                log.warning(f"!timer error: {error}")
                await interaction.followup.send("❌ Insufficient permissions for that role.", ephemeral=True)

        await bot.start(token)

    try:
        await _build_and_start(intents)
    except discord.LoginFailure:
        _state["status"] = "error"
        _state["last_error"] = "Invalid bot token"
    except discord.PrivilegedIntentsRequired:
        # Riprova senza message_content: i comandi con prefisso non funzioneranno, /timer sì.
        log.warning("[snap-bot] Message Content Intent disattivato nel Developer Portal: uso solo /timer")
        intents.message_content = False
        try:
            await _build_and_start(intents)
        except Exception as e:
            _state["status"] = "error"
            _state["last_error"] = f"Abilita 'Server Members Intent' nel Discord Developer Portal ({e})"
    except Exception as e:
        _state["status"] = "error"
        _state["last_error"] = str(e)

async def start_bot():
    cfg = await get_config()
    token = (cfg.get("token") or "").strip()
    if not token:
        return False, "No token configured"
    if _state["status"] in ("online", "starting"):
        return False, f"Bot already {_state['status']}"
    _state["status"] = "starting"
    _state["last_error"] = None
    _state["loop"] = asyncio.get_event_loop()
    _state["task"] = asyncio.create_task(_run_bot(token))
    return True, "starting"

async def stop_bot():
    bot = _state["bot"]
    if bot:
        try:
            await bot.close()
        except Exception as e:
            log.warning(f"close failed: {e}")
    if _state["task"]:
        try:
            _state["task"].cancel()
        except Exception:
            pass
    _state["bot"] = None
    _state["task"] = None
    _state["status"] = "stopped"
    return True

def status():
    b = _state.get("bot")
    return {
        "status": _state["status"],
        "last_error": _state["last_error"],
        "bot_user": str(b.user) if b and b.user else None,
        "guilds": len(b.guilds) if b else 0,
    }

def set_db(db):
    _state["db"] = db


# ---------- Leaderboard ----------
async def refresh_leaderboard():
    """Post or update the leaderboard message in the configured channel."""
    if not _state["bot"] or _state["status"] != "online":
        return False, "offline"
    cfg = await get_config()
    ch_id = (cfg.get("leaderboard_channel_id") or "").strip()
    if not ch_id:
        return False, "no channel"
    db = _state["db"]
    top = await db.presser_stats.find({}, {"_id": 0}).sort("ok_count", -1).limit(15).to_list(15)
    if not top:
        lines = "_No claims yet._"
    else:
        medals = ["🥇", "🥈", "🥉"] + ["🔸"] * 20
        parts = []
        for i, r in enumerate(top):
            parts.append(f"{medals[i]} **{i+1}.** <@{r['discord_id']}> — **{r['ok_count']}** OKs")
        lines = "\n".join(parts)

    embed = discord.Embed(
        title=cfg.get("leaderboard_title", "🏆 Top Claimers"),
        description=f"{cfg.get('leaderboard_desc','')}\n\n{lines}",
        color=cfg.get("leaderboard_color", 0xFACC15),
    )
    ft = (cfg.get("footer_text") or "").strip()
    if ft:
        embed.set_footer(text=ft)
    try:
        ch = _state["bot"].get_channel(int(ch_id)) or await _state["bot"].fetch_channel(int(ch_id))
        msg_id = (cfg.get("leaderboard_message_id") or "").strip()
        if msg_id:
            try:
                msg = await ch.fetch_message(int(msg_id))
                await msg.edit(embed=embed)
                return True, "edited"
            except Exception:
                pass
        new = await ch.send(embed=embed)
        await save_config({"leaderboard_message_id": str(new.id)})
        return True, "posted"
    except Exception as e:
        log.warning(f"leaderboard: {e}")
        return False, str(e)


async def send_broadcast(override: dict = None):
    """Send an admin-defined embed to broadcast channel."""
    if not _state["bot"] or _state["status"] != "online":
        return False, "offline"
    cfg = await get_config()
    if override:
        cfg = {**cfg, **override}
    ch_id = (cfg.get("broadcast_channel_id") or "").strip()
    if not ch_id:
        return False, "no channel"
    try:
        ch = _state["bot"].get_channel(int(ch_id)) or await _state["bot"].fetch_channel(int(ch_id))
        embed = discord.Embed(
            title=cfg.get("broadcast_title", "Announcement"),
            description=cfg.get("broadcast_desc", ""),
            color=cfg.get("broadcast_color", 0xFACC15),
        )
        ft = (cfg.get("footer_text") or "").strip()
        if ft:
            embed.set_footer(text=ft)
        await ch.send(embed=embed)
        return True, "sent"
    except Exception as e:
        return False, str(e)


# ---------- Maintenance ----------
async def announce_maintenance(enabled: bool):
    """Post maintenance status to broadcast channel."""
    if not _state["bot"] or _state["status"] != "online":
        return False, "offline"
    cfg = await get_config()
    ch_id = (cfg.get("broadcast_channel_id") or "").strip()
    if not ch_id:
        return False, "no broadcast channel"
    try:
        ch = _state["bot"].get_channel(int(ch_id)) or await _state["bot"].fetch_channel(int(ch_id))
        if enabled:
            embed = discord.Embed(
                title=cfg.get("maintenance_title", "🛠 Maintenance in progress"),
                description=cfg.get("maintenance_desc", "The bot is temporarily down for maintenance."),
                color=0xef4444,
            )
        else:
            embed = discord.Embed(
                title=cfg.get("back_online_title", "✅ We're back"),
                description=cfg.get("back_online_desc", "Everything is operational again."),
                color=0x22c55e,
            )
        ft = (cfg.get("footer_text") or "").strip()
        if ft:
            embed.set_footer(text=ft)
        await ch.send(embed=embed)
        return True, "sent"
    except Exception as e:
        log.warning(f"announce_maintenance: {e}")
        return False, str(e)
