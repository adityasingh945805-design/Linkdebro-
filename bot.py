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
from motor.motor_asyncio import AsyncIOMotorClient

# ----------------- CREDENTIALS & CONFIG -----------------
API_ID = 36244302
API_HASH = "5e844495cd20f53c82d84f97289e3b73"
BOT_TOKEN = "9072774703:AAEXziVGAuhTQbsqv2KF1APQt39172pjp3Y"
BOT_USERNAME = "Linkdebroo_bot"

# Channels
DUMP_CHANNEL = -1003449060305
FORCE_SUB_CHANNEL = -1002665537234
FSUB_INVITE_LINK = "https://t.me/+XVSXpI-nHbM4MTRl"

OWNER_ID = 7712648594
PORT = int(os.environ.get("PORT", "8080"))

# Auto-delete time: 30 minutes
AUTO_DELETE_TIME = 30 * 60

# Batch tracking: {user_id: [msg_id1, msg_id2, ...]}
BATCH_COLLECTOR = {}

# ----------------- MONGODB SETUP -----------------
MONGO_URL = os.environ.get(
    "MONGO_URL",
    "mongodb+srv://kankit28470_db_user:MyBotPass123@linkdebroo.0kiysn1.mongodb.net/naya_bot_db?retryWrites=true&w=majority"
)

# Async MongoDB client and collection
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["naya_bot_db"]
users_collection = db["users"]

async def save_user(user_id: int):
    try:
        await users_collection.update_one(
            {"_id": user_id},
            {"$set": {"user_id": user_id}},
            upsert=True
        )
    except Exception as e:
        print(f"Error saving user to MongoDB: {e}")

async def get_all_users():
    try:
        users = []
        async for doc in users_collection.find({}, {"_id": 1}):
            users.append(doc["_id"])
        return users
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []

async def total_users_count():
    try:
        return await users_collection.count_documents({})
    except Exception as e:
        print(f"Error counting users: {e}")
        return 0

# ----------------- CLIENT -----------------
app = Client(
    "linkdebro_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ----------------- HELPERS -----------------
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
    await asyncio.sleep(AUTO_DELETE_TIME)
    try:
        await client.delete_messages(chat_id=chat_id, message_ids=message_ids)
    except Exception:
        pass
    try:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=info_msg_id,
            text="⏳ **Time Up!** 30 minute poore ho gaye hain, aapka content security ke liye auto-delete kar diya gaya hai."
        )
    except Exception:
        pass

# ----------------- /start HANDLER -----------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    await save_user(user_id)

    if len(message.command) > 1:
        param = message.command[1]

        # Force Subscribe Check
        is_subbed = await check_fsub(client, user_id)
        if not is_subbed:
            btn = [
                [InlineKeyboardButton("📢 Join Channel", url=FSUB_INVITE_LINK)],
                [InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{BOT_USERNAME}?start={param}")]
            ]
            await message.reply_text(
                "⚠️ **Access Denied!**\n\nFile paane ke liye pehle hamara channel join karein.",
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return

        decoded = decode_data(param)
        if not decoded:
            await message.reply_text("❌ Invalid link.")
            return

        msg_ids = []
        if decoded.startswith("f_"):
            msg_ids.append(int(decoded.split("_")[1]))
        elif decoded.startswith("b_"):
            # Format: b_id1-id2-id3
            ids_str = decoded.split("_")[1]
            msg_ids = [int(i) for i in ids_str.split("-") if i.isdigit()]

        if not msg_ids:
            await message.reply_text("❌ Koi file nahi mili.")
            return

        sent_messages = []
        for mid in msg_ids:
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
                "⚠️ **Notice:** Ye content agle **30 minute** me auto-delete ho jayega. Jald se jald save kar lein!"
            )
            asyncio.create_task(auto_delete_task(client, user_id, sent_messages, info_msg.id))
        else:
            await message.reply_text("❌ File fetch karne me error aayi.")
        return

    await message.reply_text(
        f"👋 **Namaste {message.from_user.mention}!**\n\n"
        "• Single file link ke liye direct video ya pic bhejo.\n"
        "• Ek sath multiple files ka single link banane ke liye `/batch` use karo."
    )

# ----------------- BATCH FLOW (/batch -> uploads -> /done) -----------------
@app.on_message(filters.command("batch") & filters.user(OWNER_ID) & filters.private)
async def batch_start(client: Client, message: Message):
    BATCH_COLLECTOR[OWNER_ID] = []
    await message.reply_text(
        "📦 **Batch Mode Active!**\n\n"
        "Ab ek ek karke ya select karke saari videos/photos bhejo.\n"
        "Jab sab upload ho jayein, toh **`/done`** command send karo."
    )

@app.on_message(filters.command("done") & filters.user(OWNER_ID) & filters.private)
async def batch_done(client: Client, message: Message):
    if OWNER_ID not in BATCH_COLLECTOR or not BATCH_COLLECTOR[OWNER_ID]:
        await message.reply_text("❌ Koi files upload nahi ki gayi hain. Pehle `/batch` karke files bhejo.")
        return

    file_ids = BATCH_COLLECTOR.pop(OWNER_ID)
    encoded_ids = "-".join(map(str, file_ids))
    share_code = encode_data(f"b_{encoded_ids}")
    share_url = f"https://t.me/{BOT_USERNAME}?start={share_code}"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share Batch", url=f"https://t.me/share/url?url={share_url}")],
        [InlineKeyboardButton("Open Batch", url=share_url)]
    ])

    await message.reply_text(
        f"🎉 **Batch Link Ban Gaya!**\n\n"
        f"📁 Total Files: `{len(file_ids)}`\n"
        f"🔗 Link: `{share_url}`\n\n"
        f"⏱ *User ke paas 30 min me content auto-delete ho jayega.*",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

@app.on_message(filters.command("cancel") & filters.user(OWNER_ID) & filters.private)
async def batch_cancel(client: Client, message: Message):
    if OWNER_ID in BATCH_COLLECTOR:
        del BATCH_COLLECTOR[OWNER_ID]
        await message.reply_text("❌ Batch upload cancel kar diya gaya.")
    else:
        await message.reply_text("Koi active batch process nahi tha.")

# ----------------- MEDIA UPLOAD HANDLER -----------------
@app.on_message((filters.video | filters.photo | filters.document) & filters.private)
async def media_handler(client: Client, message: Message):
    user_id = message.from_user.id
    await save_user(user_id)

    # 1. AGAR USER BATCH MODE MEIN HAI
    if user_id in BATCH_COLLECTOR:
        try:
            copied = await client.copy_message(
                chat_id=DUMP_CHANNEL,
                from_chat_id=user_id,
                message_id=message.id
            )
            BATCH_COLLECTOR[user_id].append(copied.id)
            total = len(BATCH_COLLECTOR[user_id])
            await message.reply_text(f"📥 File #{total} batch me add ho gayi. Aur bhejo ya `/done` likho.")
        except Exception as e:
            await message.reply_text(f"❌ Batch upload error: `{e}`")
        return

    # 2. AGAR NORMAL SINGLE UPLOAD HAI
    status_msg = await message.reply_text("⏳ Processing...")
    try:
        copied = await client.copy_message(
            chat_id=DUMP_CHANNEL,
            from_chat_id=user_id,
            message_id=message.id
        )

        share_code = encode_data(f"f_{copied.id}")
        share_url = f"https://t.me/{BOT_USERNAME}?start={share_code}"

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share Link", url=f"https://t.me/share/url?url={share_url}")],
            [InlineKeyboardButton("Open Link", url=share_url)]
        ])

        await status_msg.edit_text(
            f"✅ **Aapka Single File Link:**\n\n`{share_url}`\n\n"
            f"⏱ *User access ke 30 min baad file chat se auto-delete hogi.*",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: `{e}`\nCheck karo bot Dump Channel me Admin hai ya nahi.")

# ----------------- ADMIN COMMANDS -----------------
@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats_handler(client: Client, message: Message):
    count = await total_users_count()
    await message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: `{count}`\n"
        f"👑 Admin ID: `{OWNER_ID}`\n"
        f"⏱ Auto-Delete: `30 Minutes`"
    )

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_handler(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("⚠️ Post par **reply** karke `/broadcast` likhein.")
        return

    target_msg = message.reply_to_message
    users = await get_all_users()
    total = len(users)

    if total == 0:
        await message.reply_text("❌ Abhi koi user record nahi hai.")
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
            try:
                await target_msg.copy(chat_id=uid)
                success += 1
            except Exception:
                failed += 1
        except (UserIsBlocked, InputUserDeactivated):
            failed += 1
        except Exception:
            failed += 1

    await status.edit_text(f"✅ **Broadcast Completed!**\nSent: `{success}`\nFailed: `{failed}`")

# ----------------- WEB SERVER (RENDER KEEP-ALIVE) -----------------
async def web_server():
    app_web = web.Application()
    app_web.router.add_get("/", lambda _: web.Response(text="Bot is Active!"))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    await web_server()
    await app.start()
    print("Bot is successfully running with MongoDB...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop.run_until_complete(main())
