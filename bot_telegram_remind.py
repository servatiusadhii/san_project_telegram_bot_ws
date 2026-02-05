from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from datetime import datetime
import os

TOKEN = os.getenv("BOT_TOKEN")

MENU = ReplyKeyboardMarkup(
    [
        ["1️⃣ Hari & waktu", "2️⃣ Cuaca hari ini"],
        ["📝 Tulis catatan", "📋 Lihat catatan"],
        ["❌ Exit"],
    ],
    resize_keyboard=True
)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Halo!\nPilih menu di bawah 👇",
        reply_markup=MENU
    )

# ===== HANDLE TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # === MENU 1 ===
    if text == "1️⃣ Hari & waktu":
        now = datetime.now()
        await update.message.reply_text(
            f"📅 Hari: {now.strftime('%A')}\n"
            f"🗓️ Tanggal: {now.strftime('%d %B %Y')}\n"
            f"⏰ Jam: {now.strftime('%H:%M:%S')}"
        )

    # === MENU 2 ===
    elif text == "2️⃣ Cuaca hari ini":
        await update.message.reply_text(
            "🌤️ Cuaca hari ini:\n"
            "- Suhu: ±30°C\n"
            "- Kondisi: cerah berawan\n\n"
            "📌 Perkiraan sederhana"
        )

    # === MENU CATATAN ===
    elif text == "📝 Tulis catatan":
        context.user_data["state"] = "WAIT_NOTE"
        await update.message.reply_text("✍️ Ketik catatan lu:")

    elif text == "📋 Lihat catatan":
        note = context.user_data.get("note")
        if note:
            await update.message.reply_text(f"📌 Catatan lu:\n{note}")
        else:
            await update.message.reply_text("❗ Belum ada catatan.")

    # === EXIT ===
    elif text == "❌ Exit":
        context.user_data.clear()
        await update.message.reply_text(
            "👋 Sampai jumpa!",
            reply_markup=ReplyKeyboardRemove()
        )

    # === NANGKAP JAWABAN CATATAN ===
    elif context.user_data.get("state") == "WAIT_NOTE":
        context.user_data["note"] = text
        context.user_data.pop("state", None)
        await update.message.reply_text(
            "✅ Catatan berhasil disimpan!",
            reply_markup=MENU
        )

    # === DEFAULT ===
    else:
        await update.message.reply_text(
            "❓ Pilih menu dari tombol ya.",
            reply_markup=MENU
        )

# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
