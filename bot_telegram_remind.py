from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from datetime import datetime
import asyncio
import random
import os

TOKEN = os.getenv("BOT_TOKEN")

MENU = ReplyKeyboardMarkup(
    [
        ["📅 Hari ini", "📝 Catatan"],
        ["⏰ Reminder", "😊 Mood"],
        ["📊 Ringkasan", "❌ Exit"],
    ],
    resize_keyboard=True
)

# ---------- UTIL ----------
def now_text():
    now = datetime.now()
    return (
        f"📅 {now.strftime('%A, %d %B %Y')}\n"
        f"🕒 {now.strftime('%H:%M:%S')}"
    )

def empathic_reply(text):
    text = text.lower()
    if any(x in text for x in ["capek", "lelah", "pusing"]):
        return "😮‍💨 Kedengeran capek ya. Jangan lupa istirahat bentar."
    if any(x in text for x in ["sedih", "down", "galau"]):
        return "💙 Gue dengerin. Pelan-pelan ya, semua lewat."
    if any(x in text for x in ["bingung", "stuck"]):
        return "🤔 Bingung itu wajar. Mau bikin catatan atau reminder?"
    return None

# ---------- COMMAND ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Halo!\n"
        "Gue asisten pribadi lo.\n\n"
        f"{now_text()}\n\n"
        "Pilih menu di bawah 👇",
        reply_markup=MENU
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Dibatalkan.\nPilih menu lagi 👇",
        reply_markup=MENU
    )

# ---------- MENU HANDLER ----------
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📅 Hari ini":
        await update.message.reply_text(now_text())

    elif text == "📝 Catatan":
        context.user_data["mode"] = "note"
        await update.message.reply_text(
            "📝 MODE CATATAN\n\n"
            "Ketik catatan lo.\n"
            "Contoh:\n"
            "- beli susu\n"
            "- ide bisnis\n\n"
            "Ketik /batal untuk keluar"
        )

    elif text == "⏰ Reminder":
        context.user_data["mode"] = "reminder"
        await update.message.reply_text(
            "⏰ MODE REMINDER\n\n"
            "Format:\n"
            "HH:MM | pesan\n\n"
            "Contoh:\n"
            "09:00 | meeting\n\n"
            "Ketik /batal untuk keluar"
        )

    elif text == "😊 Mood":
        kb = ReplyKeyboardMarkup(
            [["😊 Senang", "😐 Biasa", "😞 Capek"]],
            resize_keyboard=True
        )
        context.user_data["mode"] = "mood"
        await update.message.reply_text("Mood lo hari ini gimana?", reply_markup=kb)

    elif text == "📊 Ringkasan":
        notes = len(context.user_data.get("notes", []))
        mood = context.user_data.get("mood", "Belum diisi")
        await update.message.reply_text(
            "📊 RINGKASAN HARI INI\n\n"
            f"{now_text()}\n"
            f"📝 Catatan: {notes}\n"
            f"😊 Mood: {mood}"
        )

    elif text == "❌ Exit":
        context.user_data.clear()
        await update.message.reply_text("👋 Sampai ketemu lagi!")

# ---------- TEXT HANDLER ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    mode = context.user_data.get("mode")

    if mode == "note":
        context.user_data.setdefault("notes", []).append(text)
        context.user_data["mode"] = None
        await update.message.reply_text("✅ Catatan tersimpan.", reply_markup=MENU)

    elif mode == "reminder":
        try:
            time_part, msg = text.split("|", 1)
            hour, minute = map(int, time_part.strip().split(":"))

            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0)
            delay = (target - now).total_seconds()

            if delay < 0:
                await update.message.reply_text("⛔ Waktunya sudah lewat.")
                return

            async def send_reminder():
                await asyncio.sleep(delay)
                await update.message.reply_text(f"⏰ Reminder:\n{msg.strip()}")

            asyncio.create_task(send_reminder())
            context.user_data["mode"] = None
            await update.message.reply_text("⏳ Reminder diset.", reply_markup=MENU)

        except:
            await update.message.reply_text("❌ Format salah. Ketik /batal")

    elif mode == "mood":
        context.user_data["mood"] = text
        context.user_data["mode"] = None
        await update.message.reply_text(
            f"😊 Mood tersimpan: {text}",
            reply_markup=MENU
        )

    else:
        reply = empathic_reply(text)
        if reply:
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text(
                "Pilih menu ya 👇",
                reply_markup=MENU
            )

# ---------- MAIN ----------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("batal", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))

    print("Bot berjalan...")
    app.run_polling()
