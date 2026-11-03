import os
import asyncio
import base64
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ----------------- CREDENTIALS & CONFIG -----------------
API_ID = 36244302
API_HASH = "5e844495cd20f53c82d84f97289e3b73"
BOT_TOKEN = "9072774703:AAEXziVGAuhTQbsqv2KF1APQt39172pjp3Y"
BOT_USERNAME = "Linkdebroo_bot"

# Channel Details
DUMP_CHANNEL = -1003449060305
FORCE_SUB_CHANNEL = -1003449060305
FSUB_INVITE_LINK = "https://t.me/+XVSXpI-nHbM4MTRl"

OWNER_ID = 7712648594
PORT = int(os.environ.get("PORT", "8080"))

# ----------------- CLIENT INITIALIZATION -----------------
app = Client(
    "linkdebro_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ----------------- HELPER FUNCTIONS -----------------
def encode_id(msg_id: int) -> str:
    text = f"file_{msg_id}"
    return base64.urlsafe_b64encode(text.encode("ascii")).decode("ascii").rstrip("=")

def decode_id(base64_str: str) -> int:
    try:
        padding = "=" * (4 - (len(base64_str) % 4)) if len(base64_str) % 4 != 0 else ""
        decoded = base64.urlsafe_b64decode((base64_str + padding).encode("ascii")).decode("ascii")
        if decoded.startswith("file_"):
            return int(decoded.split("_")[1])
    except Exception:
        pass
    return 0

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

# ----------------- HANDLERS -----------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

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

        # Fetch and deliver file directly via Telegram Cloud
        dump_msg_id = decode_id(param)
        if dump_msg_id == 0:
            await message.reply_text("❌ Invalid ya expired link.")
            return

        try:
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=DUMP_CHANNEL,
                message_id=dump_msg_id
            )
        except Exception as e:
            await message.reply_text(f"❌ File deliver karne me error aayi: `{e}`")
        return

    # Default Start Message
    await message.reply_text(
        f"👋 **Namaste {message.from_user.mention}!**\n\n"
        "Mujhe koi bhi video ya photo bhejo, mai uska permanent share link bana dunga."
    )

@app.on_message((filters.video | filters.photo | filters.document) & filters.private)
async def upload_handler(client: Client, message: Message):
    user_id = message.from_user.id
    status_msg = await message.reply_text("⏳ Processing...")

    try:
        # Direct server-to-server copy (Zero disk usage)
        copied = await client.copy_message(
            chat_id=DUMP_CHANNEL,
            from_chat_id=user_id,
            message_id=message.id
        )

        share_code = encode_id(copied.id)
        share_url = f"https://t.me/{BOT_USERNAME}?start={share_code}"

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share Link", url=f"https://t.me/share/url?url={share_url}")],
            [InlineKeyboardButton("Open Link", url=share_url)]
        ])

        await status_msg.edit_text(
            f"✅ **Aapka Link Ready Hai:**\n\n`{share_url}`",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: `{e}`\n\n*(Check karein ki bot channel me Admin hai ya nahi)*")

# ----------------- DUMMY SERVER FOR RENDER -----------------
async def web_server():
    app_web = web.Application()
    app_web.router.add_get("/", lambda _: web.Response(text="Linkdebroo Bot is Active!"))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    await web_server()
    await app.start()
    print("Bot is successfully running...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

