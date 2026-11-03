# app.py  (FIXED VERSION)
# Web server (FastAPI) + Telegram bot (Pyrogram) ek hi process me.

import os
import re
import math
import asyncio
import secrets
import logging
import traceback
from contextlib import asynccontextmanager
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from pyrogram import Client, filters, enums, raw
from pyrogram.errors import (
    FloodWait, UserNotParticipant, AccessTokenInvalid, ApiIdInvalid,
)
from pyrogram.file_id import FileId
from pyrogram.session import Session, Auth
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated,
)

from config import Config
from database import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)


class HideDLFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /dl/" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(HideDLFilter())

# =====================================================================
# BOT SETUP
# =====================================================================

bot = Client(
    "SimpleStreamBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True,
)

multi_clients = {}
work_loads = {}
class_cache = {}

# /  page par yahi dikhega -> bot ka status turant pata chal jayega
bot_state = {"ready": False, "username": None, "error": None}
_bot_task = None
_force_link_cache = {"url": None}


# =====================================================================
# MULTI-CLIENT (OPTIONAL: MULTI_TOKEN1, MULTI_TOKEN2 ... env vars)
# =====================================================================

def parse_multi_tokens():
    items = sorted(
        (k, v.strip()) for k, v in os.environ.items()
        if k.startswith("MULTI_TOKEN") and v.strip()
    )
    return {i + 1: token for i, (_, token) in enumerate(items)}


async def start_client(client_id, token):
    try:
        print(f"Starting extra client {client_id}...")
        client = await Client(
            name=f"stream_{client_id}",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=token,
            no_updates=True,
            in_memory=True,
        ).start()
        work_loads[client_id] = 0
        multi_clients[client_id] = client
        print(f"✅ Client {client_id} started.")
    except Exception as e:
        print(f"!!! Client {client_id} start nahi hua: {e}")


async def initialize_clients():
    tokens = parse_multi_tokens()
    if not tokens:
        print("No extra clients. Only main bot use hoga.")
        return
    await asyncio.gather(*[start_client(i, t) for i, t in tokens.items()])
    print(f"✅ Multi-client mode: total {len(multi_clients)} clients.")


# =====================================================================
# HELPERS
# =====================================================================

def get_readable_file_size(size):
    if not size:
        return "0 B"
    labels = ["B", "KB", "MB", "GB", "TB"]
    n = 0
    size = float(size)
    while size >= 1024 and n < len(labels) - 1:
        size /= 1024
        n += 1
    return f"{size:.2f} {labels[n]}"


def mask_filename(name: str):
    if not name:
        return "Protected File"
    base, ext = os.path.splitext(name)
    pattern = re.compile(
        r"((19|20)\d{2}|4k|2160p|1080p|720p|480p|360p|HEVC|x265|BluRay|WEB-DL|HDRip)",
        re.IGNORECASE,
    )
    m = pattern.search(base)
    if m:
        title, meta = base[:m.start()].strip(" .-_"), base[m.start():]
    else:
        title, meta = base, ""
    masked = "".join(
        c if (i % 3 == 0 and c.isalnum()) else ("*" if c.isalnum() else c)
        for i, c in enumerate(title)
    )
    return f"{masked} {meta}{ext}".strip()


async def get_force_sub_link(client: Client):
    """Force-sub channel ka sahi join link banata hai."""
    if Config.FORCE_SUB_LINK:
        return Config.FORCE_SUB_LINK
    if _force_link_cache["url"]:
        return _force_link_cache["url"]
    ch = Config.FORCE_SUB_CHANNEL
    if isinstance(ch, str):  # username
        url = f"https://t.me/{ch}"
    else:
        try:
            url = await client.export_chat_invite_link(ch)
        except Exception as e:
            print(f"Force-sub invite link nahi bana: {e}")
            url = None
    _force_link_cache["url"] = url
    return url


async def is_subscribed(client: Client, user_id: int) -> bool:
    """True = user channel me hai (ya check fail hua, tab bot ko block nahi karte)."""
    try:
        member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, user_id)
        return member.status not in (
            enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED,
        )
    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"Force-sub check error (bot channel me admin hai?): {e}")
        return True


def force_sub_enabled() -> bool:
    return bool(Config.FORCE_SUB_CHANNEL) and Config.FORCE_SUB_CHANNEL != Config.STORAGE_CHANNEL


# =====================================================================
# BOT HANDLERS
# =====================================================================

@bot.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: Message):
    await message.reply_text("🏓 Pong! Bot zinda hai.")


@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if len(message.command) > 1 and message.command[1].startswith("verify_"):
        payload = message.command[1]
        unique_id = payload.split("_", 1)[1]

        if force_sub_enabled() and not await is_subscribed(client, user_id):
            link = await get_force_sub_link(client)
            rows = []
            if link:
                rows.append([InlineKeyboardButton("📢 Join Channel", url=link)])
            rows.append([InlineKeyboardButton(
                "✅ Joined", url=f"https://t.me/{Config.BOT_USERNAME}?start={payload}")])
            await message.reply_text(
                "**You Must Join Our Channel To Get The Link!**\n\n"
                "__Join Channel & Click '✅ Joined'.__",
                reply_markup=InlineKeyboardMarkup(rows), quote=True,
            )
            return

        final_link = f"{Config.BASE_URL}/show/{unique_id}"
        await message.reply_text(
            f"__✅ Verification Successful!\n\nCopy Link:__ `{final_link}`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=final_link)]]),
            quote=True, disable_web_page_preview=True,
        )
    else:
        await message.reply_text(
            f"👋 **Hello, {user_name}!**\n\n"
            "__Welcome To Sharing Box Bot. I Can Help You Create Permanent, "
            "Shareable Links For Your Files.__\n\n"
            "**How To Use Me:**\n\n"
            "__Just Send Or Forward Any File To Me And I will instantly give you "
            "a special link that you can share with anyone!__"
        )


async def handle_file_upload(message: Message):
    try:
        sent = await message.copy(chat_id=Config.STORAGE_CHANNEL)
        unique_id = secrets.token_urlsafe(8)
        await db.save_link(unique_id, sent.id)
        verify_link = f"https://t.me/{Config.BOT_USERNAME}?start=verify_{unique_id}"
        await message.reply_text(
            "__✅ File Uploaded!__",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Get Link Now", url=verify_link)]]),
            quote=True,
        )
    except Exception:
        print(f"!!! Upload ERROR: {traceback.format_exc()}")
        await message.reply_text("Sorry, something went wrong.")


@bot.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def file_handler(_, message: Message):
    await handle_file_upload(message)


@bot.on_chat_member_updated(filters.chat(Config.STORAGE_CHANNEL))
async def simple_gatekeeper(c: Client, upd: ChatMemberUpdated):
    try:
        new = upd.new_chat_member
        if new and new.status == enums.ChatMemberStatus.MEMBER:
            u = new.user
            if u.id == Config.OWNER_ID or u.is_self:
                return
            print(f"Gatekeeper: Kicking {u.id}")
            await c.ban_chat_member(Config.STORAGE_CHANNEL, u.id)
            await c.unban_chat_member(Config.STORAGE_CHANNEL, u.id)
    except Exception as e:
        print(f"Gatekeeper Error: {e}")


async def cleanup_channel(c: Client):
    print("Gatekeeper: Running cleanup...")
    allowed = {Config.OWNER_ID, c.me.id}
    try:
        async for m in c.get_chat_members(Config.STORAGE_CHANNEL):
            if m.user.id in allowed:
                continue
            if m.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
                continue
            try:
                print(f"Cleanup: Kicking {m.user.id}")
                await c.ban_chat_member(Config.STORAGE_CHANNEL, m.user.id)
                await asyncio.sleep(1)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"Cleanup Error: {e}")
    except Exception as e:
        print(f"Cleanup Error: {e}")


# =====================================================================
# BOT STARTUP (background me, taaki website hamesha turant up ho)
# =====================================================================

async def run_bot():
    missing = Config.missing()
    if missing:
        msg = "Ye Environment Variables set nahi hain: " + ", ".join(missing)
        bot_state["error"] = msg
        print(f"!!! {msg}")
        if {"API_ID", "API_HASH", "BOT_TOKEN"} & set(missing):
            return  # bot in ke bina start hi nahi ho sakta

    while True:
        try:
            print("Starting Telegram bot...")
            await bot.start()
            break
        except FloodWait as e:
            print(f"FloodWait: {e.value}s ruk raha hu...")
            await asyncio.sleep(e.value + 1)
        except AccessTokenInvalid:
            bot_state["error"] = "BOT_TOKEN galat/revoked hai. BotFather se naya token lo."
            print(f"!!! {bot_state['error']}")
            return
        except ApiIdInvalid:
            bot_state["error"] = "API_ID / API_HASH galat hai."
            print(f"!!! {bot_state['error']}")
            return
        except Exception as e:
            bot_state["error"] = f"Bot start error: {e}"
            print(f"!!! Bot start fail: {traceback.format_exc()}  (20s me retry)")
            try:
                await bot.stop()
            except Exception:
                pass
            await asyncio.sleep(20)

    me = await bot.get_me()
    Config.BOT_USERNAME = me.username
    bot_state.update(ready=True, username=me.username, error=None)
    print(f"✅ Bot @{me.username} start ho gaya. (Telegram me isi bot ko /start bhejo)")

    multi_clients[0] = bot
    work_loads[0] = 0
    await initialize_clients()

    # --- Storage channel check (fail hone par bot band nahi hoga) ---
    try:
        chat = await bot.get_chat(Config.STORAGE_CHANNEL)
        print(f"✅ Storage channel OK: {chat.title}")
    except Exception as e:
        print(f"!!! STORAGE_CHANNEL error: {e}")
        print("    Fix: bot ko channel me ADMIN banao & STORAGE_CHANNEL ID -100... format me do.")

    if Config.FORCE_SUB_CHANNEL:
        if Config.FORCE_SUB_CHANNEL == Config.STORAGE_CHANNEL:
            print("!!! FORCE_SUB_CHANNEL aur STORAGE_CHANNEL same hain -> force-sub band kar diya. "
                  "Alag channel do.")
        else:
            try:
                await bot.get_chat(Config.FORCE_SUB_CHANNEL)
                print("✅ Force-sub channel OK")
            except Exception as e:
                print(f"!!! Force-sub channel error (bot ko wahan admin banao): {e}")

    # --- Owner ko confirmation message ---
    if Config.OWNER_ID:
        try:
            await bot.send_message(Config.OWNER_ID, "✅ Bot start ho gaya aur online hai.")
        except Exception as e:
            print(f"Owner ko message nahi gaya (pehle bot ko /start bhejo): {e}")

    asyncio.create_task(cleanup_channel(bot))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_task
    print("--- Server start ho raha hai ---")
    await db.connect()
    _bot_task = asyncio.create_task(run_bot())
    yield
    print("--- Server band ho raha hai ---")
    if _bot_task:
        _bot_task.cancel()
    for cid, c in list(multi_clients.items()):
        try:
            await c.stop()
        except Exception:
            pass
    if bot.is_connected and 0 not in multi_clients:
        try:
            await bot.stop()
        except Exception:
            pass
    await db.disconnect()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# WEB ROUTES
# =====================================================================

@app.api_route("/", methods=["GET", "HEAD"])
async def health_check():
    """Yahan bot ka status dikhta hai: bot_ready true hona chahiye."""
    return {
        "status": "ok",
        "bot_ready": bot_state["ready"],
        "bot_username": bot_state["username"],
        "error": bot_state["error"],
    }


@app.get("/show/{unique_id}", response_class=HTMLResponse)
async def show_page(request: Request, unique_id: str):
    return templates.TemplateResponse("show.html", {"request": request})


@app.get("/api/file/{unique_id}", response_class=JSONResponse)
async def get_file_details_api(request: Request, unique_id: str):
    message_id = await db.get_link(unique_id)
    if not message_id:
        raise HTTPException(status_code=404, detail="Link expired or invalid.")
    main_bot = multi_clients.get(0)
    if not main_bot:
        raise HTTPException(status_code=503, detail="Bot is not ready.")
    try:
        message = await main_bot.get_messages(Config.STORAGE_CHANNEL, message_id)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found on Telegram.")
    media = message.document or message.video or message.audio
    if not media:
        raise HTTPException(status_code=404, detail="Media not found in the message.")

    file_name = media.file_name or "file"
    safe_name = "".join(c for c in file_name if c.isalnum() or c in (" ", ".", "_", "-")).rstrip() or "file"
    safe_name = quote(safe_name)
    mime = media.mime_type or "application/octet-stream"
    dl = f"{Config.BASE_URL}/dl/{message_id}/{safe_name}"
    return {
        "file_name": mask_filename(file_name),
        "file_size": get_readable_file_size(media.file_size),
        "is_media": mime.startswith(("video", "audio")),
        "direct_dl_link": dl,
        "mx_player_link": f"intent:{dl}#Intent;action=android.intent.action.VIEW;type={mime};end",
        "vlc_player_link": f"intent:{dl}#Intent;action=android.intent.action.VIEW;type={mime};package=org.videolan.vlc;end",
    }


class ByteStreamer:
    def __init__(self, client: Client):
        self.client = client

    @staticmethod
    async def get_location(f: FileId):
        return raw.types.InputDocumentFileLocation(
            id=f.media_id,
            access_hash=f.access_hash,
            file_reference=f.file_reference,
            thumb_size=f.thumbnail_size,
        )

    async def yield_file(self, f: FileId, index, offset, first_cut, last_cut, part_count, chunk_size):
        c = self.client
        work_loads[index] += 1
        try:
            ms = c.media_sessions.get(f.dc_id)
            if ms is None:
                if f.dc_id != await c.storage.dc_id():
                    test_mode = await c.storage.test_mode()
                    auth_key = await Auth(c, f.dc_id, test_mode).create()
                    ms = Session(c, f.dc_id, auth_key, test_mode, is_media=True)
                    await ms.start()
                    exported = await c.invoke(raw.functions.auth.ExportAuthorization(dc_id=f.dc_id))
                    await ms.invoke(raw.functions.auth.ImportAuthorization(
                        id=exported.id, bytes=exported.bytes))
                else:
                    ms = c.session
                c.media_sessions[f.dc_id] = ms

            location = await self.get_location(f)
            part = 1
            while part <= part_count:
                r = await ms.invoke(
                    raw.functions.upload.GetFile(location=location, offset=offset, limit=chunk_size),
                    retries=0,
                )
                if not isinstance(r, raw.types.upload.File):
                    break
                chunk = r.bytes
                if not chunk:
                    break
                if part_count == 1:
                    yield chunk[first_cut:last_cut]
                elif part == 1:
                    yield chunk[first_cut:]
                elif part == part_count:
                    yield chunk[:last_cut]
                else:
                    yield chunk
                part += 1
                offset += chunk_size
        finally:
            work_loads[index] -= 1


@app.get("/dl/{mid}/{fname}")
async def stream_media(r: Request, mid: int, fname: str):
    if not work_loads:
        raise HTTPException(503, "Bot abhi ready nahi hai.")
    client_id = min(work_loads, key=work_loads.get)
    c = multi_clients.get(client_id)
    if not c:
        raise HTTPException(503)

    streamer = class_cache.get(c) or ByteStreamer(c)
    class_cache[c] = streamer
    try:
        msg = await c.get_messages(Config.STORAGE_CHANNEL, mid)
        m = msg.document or msg.video or msg.audio
        if not m or msg.empty:
            raise FileNotFoundError

        fid = FileId.decode(m.file_id)
        fsize = m.file_size
        rh = r.headers.get("Range", "")
        fb, ub = 0, fsize - 1
        if rh:
            try:
                start, _, end = rh.replace("bytes=", "").partition("-")
                fb = int(start) if start else 0
                if end:
                    ub = int(end)
            except ValueError:
                raise HTTPException(416)
        ub = min(ub, fsize - 1)
        if fb < 0 or fb > ub:
            raise HTTPException(416)

        req_len = ub - fb + 1
        cs = 1024 * 1024
        off = (fb // cs) * cs
        first_cut = fb - off
        last_cut = (ub % cs) + 1
        part_count = math.ceil((ub + 1 - off) / cs)

        body = streamer.yield_file(fid, client_id, off, first_cut, last_cut, part_count, cs)
        name = quote(m.file_name or "file")
        headers = {
            "Content-Type": m.mime_type or "application/octet-stream",
            "Accept-Ranges": "bytes",
            "Content-Disposition": f"inline; filename*=UTF-8''{name}",
            "Content-Length": str(req_len),
        }
        if rh:
            headers["Content-Range"] = f"bytes {fb}-{ub}/{fsize}"
        return StreamingResponse(body, status_code=206 if rh else 200, headers=headers)
    except FileNotFoundError:
        raise HTTPException(404)
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500)


# ===================================================================
