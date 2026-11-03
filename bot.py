import os
import asyncio

# --- Python event loop initialization ---
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import base64
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait, InputUserDeactivated, UserIsBlocked

# ----------------- CREDENTIALS & CONFIG -----------------
API_ID = 36244302
API_HASH = "5e844495cd20f53c82d84f97289e3b73"
BOT_TOKEN = "9072774703:AAEXziVGAuhTQbsqv2KF1APQt39172pjp3Y"
BOT_USERNAME = "Linkdebroo_bot"

# Channels
DUMP_CHANNEL = -1003449060305
FORCE_SUB_CHANNEL = -1003449060305
FSUB_INVITE_LINK = "https://t.me/+XVSXpI-nHbM4MTRl"

OWNER_ID = 7712648594
PORT = int(os.environ.get("PORT", "8080"))

# Auto delete timer (30 minutes in seconds)
AUTO_DELETE_TIME = 30 * 60

# In-memory batch state tracking for Admin
BATCH_STATE = {}

# Persistent user file
USERS_FILE = "users.txt"

def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

def save_user(user_id: int):
    users = load_users()
    if user_id not in users:
        with open(USERS_FILE, "a") as f:
            f.write(f"{user_id}\n")

# ----------------- CLIENT -----------------
app = Client(
    "linkdebro_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ----------------- ENCODING & HELPERS -----------------
def encode_data(data_str: str) -> str:
    return base64.urlsafe_b64encode(data_str.encode("ascii")).decode("ascii").rstrip("=")

def decode_data(base64_str: str) -> str:
    try:
        padding = "=" * (4 - (len(base64_str) % 4)) if len(base64_str) % 4 != 0 else ""
        return base64.urlsafe_b64decode((base64_str + padding).encode("ascii")).decode("ascii")
    except Exception:
        return ""

async def check_fsub(client: Client, user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in ["kicked", "left"]:
            return False
        return True
    except UserNotParticipant:
        return False
    except Exception:
        return True

async def auto_delete_task(client: Client, chat_id: int, message_ids: list, info_msg_id: int):
    # Wait for 30 minutes
    await asyncio.sleep(AUTO_DELETE_TIME)
    try:
        # Delete delivered files
        await client.delete_messages(chat_id=chat_id, message_ids=message_ids)
    except Exception:
        pass
    try:
        # Edit/Delete warning message
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=info_msg_id,
            text="⏳ **Time expired!** Aapki file 30 minute poore hone par security ke liye auto-delete kar di gayi hai."
        )
    except Exception:
        pass

# ----------------- USER HANDLERS -----------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    save_user(user_id)

    # Deep-link access check
    if len(message.command) > 1:
        param = message.command[1]

        # Force Subscribe Verification
        is_subbed = await check_fsub(client, user_id)
        if not is_subbed:
            btn = [
                [InlineKeyboardButton("📢 Join Channel", url=FSUB_INVITE_LINK)],
                [InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{BOT_USERNAME}?start={param}")]
            ]
            await message.reply_text(
                "⚠️ **Access Denied!**\n\nFile download karne ke liye pehle hamara channel join karein.",
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return

        decoded = decode_data(param)
        if not decoded:
            await message.reply_text("❌ Invalid ya expired link.")
            return

        msg_ids_to_send = []
        if decoded.startswith("file_"):
            msg_ids_to_send.append(int(decoded.split("_")[1]))
        elif decoded.startswith("batch_"):
            # Format: batch_startID_endID
            parts = decoded.split("_")
            first_id = int(parts[1])
            last_id = int(parts[2])
            msg_ids_to_send = list(range(first_id, last_id + 1))
        else:
            await message.reply_text("❌ Unknown link structure.")
            return

        sent_messages = []
        for mid in msg_ids_to_send:
            try:
                sent = await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=DUMP_CHANNEL,
                    message_id=mid
                )
                sent_messages.append(sent.id)
                await asyncio.sleep(0.3)
            except Exception:
                continue

        if sent_messages:
            info_msg = await message.reply_text(
                "⚠️ **Dhyan Dein:** Ye file agle **30 minute** me automatic delete ho jayegi. Kripya ise save ya forward kar lein!"
            )
            # Run background delete task
            asyncio.create_task(auto_delete_task(client, user_id, sent_messages, info_msg.id))
        else:
            await message.reply_text("❌ File fetch karne me dikkat aayi ya file exist nahi karti.")
        return

    # Normal /start
    await message.reply_text(
        f"👋 **Namaste {message.from_user.mention}!**\n\n"
        "Mujhe koi bhi video ya photo bhejo, mai uska shareable link generate kar dunga.\n\n"
        "⏱ **Feature:** User ke paas file 30 minute baad auto-delete ho jayegi."
    )

# ----------------- SINGLE UPLOAD -----------------
@app.on_message((filters.video | filters.photo | filters.document) & filters.private)
async def upload_handler(client: Client, message: Message):
    user_id = message.from_user.id
    save_user(user_id)

    # Check if admin is currently in /batch mode
    if user_id in BATCH_STATE:
        return

    status_msg = await message.reply_text("⏳ Processing...")

    try:
        copied = await client.copy_message(
            chat_id=DUMP_CHANNEL,
            from_chat_id=user_id,
            message_id=message.id
        )

        share_code = encode_data(f"file_{copied.id}")
        share_url = f"https://t.me/{BOT_USERNAME}?start={share_code}"

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share Link", url=f"https://t.me/share/url?url={share_url}")],
            [InlineKeyboardButton("Open Link", url=share_url)]
        ])

        await status_msg.edit_text(
            f"✅ **Aapka Single File Link Ready Hai:**\n\n`{share_url}`\n\n"
            f"⏱ *Note: User ke download karne ke 30 min baad content auto-delete ho jayega.*",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: `{e}`\n\n*(Check karo bot Dump Channel me Admin hai ya nahi)*")

# ----------------- ADMIN COMMANDS (/batch, /stats, /broadcast) -----------------
@app.on_message(filters.command("batch") & filters.user(OWNER_ID) & filters.private)
async def batch_handler(client: Client, message: Message):
    BATCH_STATE[OWNER_ID] = {"step": 1, "first_id": None, "last_id": None}
    await message.reply_text(
        "📦 **Batch Creation Mode Chalu Ho Gaya!**\n\n"
        "Ab Dump Channel se **First Message** ka Post Link bhejo (e.g. `https://t.me/c/3449060305/10`)\n\n"
        "Ya cancel karne ke liye `/cancel` likhein."
    )

@app.on_message(filters.command("cancel") & filters.user(OWNER_ID) & filters.private)
async def cancel_batch(client: Client, message: Message):
    if OWNER_ID in BATCH_STATE:
        del BATCH_STATE[OWNER_ID]
        await message.reply_text("❌ Batch creation cancel kar diya gaya.")
    else:
        await message.reply_text("Koi active batch process nahi chal raha hai.")

@app.on_message(filters.text & filters.user(OWNER_ID) & filters.private)
async def batch_link_collector(client: Client, message: Message):
    if OWNER_ID not in BATCH_STATE:
        return

    text = message.text.strip()
    if not ("/c/" in text or "t.me/" in text):
        await message.reply_text("❌ Kripya channel post ka valid link bhejein.")
        return

    try:
        post_id = int(text.split("/")[-1])
    except Exception:
        await message.reply_text("❌ Link se Post ID nikalne me error aayi.")
        return

    state = BATCH_STATE[OWNER_ID]

    if state["step"] == 1:
        state["first_id"] = post_id
        state["step"] = 2
        await message.reply_text(
            f"✅ First Message ID: `{post_id}` save ho gayi.\n\n"
            f"Ab Batch ki **Last Message** ka Post Link bhejo:"
        )
    elif state["step"] == 2:
        state["last_id"] = post_id
        first_id = state["first_id"]
        last_id = state["last_id"]

        if first_id > last_id:
            first_id, last_id = last_id, first_id

        del BATCH_STATE[OWNER_ID]

        batch_code = encode_data(f"batch_{first_id}_{last_id}")
        share_url = f"https://t.me/{BOT_USERNAME}?start={batch_code}"

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share Batch", url=f"https://t.me/share/url?url={share_url}")],
            [InlineKeyboardButton("Open Batch", url=share_url)]
        ])

        total_files = (last_id - first_id) + 1
        await message.reply_text(
            f"🎉 **Batch Link Ready!**\n\n"
            f"📁 Total Files: `{total_files}`\n"
            f"🔗 Link: `{share_url}`\n\n"
            f"⏱ *Note: User ke lene ke 30 minute baad saari files auto-delete ho jayengi.*",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats_handler(client: Client, message: Message):
    users = load_users()
    await message.reply_text(
        f"📊 **Bot Live Statistics**\n\n"
        f"👥 Total Users: `{len(users)}`\n"
        f"👑 Admin: `{OWNER_ID}`\n"
        f"📢 Dump Channel: `{DUMP_CHANNEL}`\n"
        f"⏱ Auto Delete: `30 Minutes`"
    )

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_handler(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("⚠️ Kisi post par **reply** karke `/broadcast` likho.")
        return

    target_msg = message.reply_to_message
    users = load_users()
    total = len(users)

    if total == 0:
        await message.reply_text("❌ Koi user database me nahi hai.")
        return

    status = await message.reply_text(f"🚀 Broadcasting to `{total}` users...")
    success, failed = 0, 0

    for uid in users:
        try:
            await target_msg.copy(chat_id=uid)
            success += 1
            await asyncio.sleep(0.05)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await target_msg.copy(chat_id=uid)
            success += 1
        except (UserIsBlocked, InputUserDeactivated):
            failed += 1
        except Exception:
            failed += 1

    await status.edit_text(
        f"✅ **Broadcast Done!**\nSent: `{success}`\nFailed/Blocked: `{failed}`"
    )

# ----------------- KEEP-ALIVE SERVER -----------------
async def web_server():
    app_web = web.Application()
    app_web.router.add_get("/", lambda _: web.Response(text="Bot is running!"))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    await web_server()
    await app.start()
    print("Bot is successfully running...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop.run_until_complete(main())
