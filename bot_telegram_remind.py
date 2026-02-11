from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from datetime import datetime, time
import os

TOKEN = os.getenv("BOT_TOKEN")

# ===== MENU =====
MENU = ReplyKeyboardMarkup(
    [
        ["💸 Catat Pengeluaran", "💰 Catat Pemasukan"],
        ["📊 Ringkasan Hari Ini"],
        ["📄 Lihat Semua Catatan"],
        ["❌ Exit"],
    ],
    resize_keyboard=True
)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    context.user_data.setdefault("records", [])

    # reminder tiap pagi jam 08:00
    context.job_queue.run_daily(
        morning_reminder,
        time=time(hour=8, minute=0),
        chat_id=chat_id,
        name=str(chat_id)
    )

    await update.message.reply_text(
        "👋 Halo bos!\n"
        "⏰ Reminder target pengeluaran aktif tiap jam 08:00.\n"
        "Pilih menu 👇",
        reply_markup=MENU
    )

# ===== REMINDER PAGI =====
async def morning_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id

    user_data = context.application.user_data.setdefault(chat_id, {})
    user_data["state"] = "DAILY_LIMIT"
    user_data["daily_date"] = datetime.now().date()

    await context.bot.send_message(
        chat_id=chat_id,
        text="☀️ Pagi bos!\nTarget maksimal pengeluaran hari ini berapa?"
    )

# ===== HANDLE TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    state = context.user_data.get("state")

    # ===== SET TARGET HARIAN =====
    if state == "DAILY_LIMIT":
        context.user_data["daily_limit"] = int(text)
        context.user_data["daily_date"] = datetime.now().date()
        context.user_data.pop("state", None)

        await update.message.reply_text(
            f"✅ Target hari ini diset: Rp {int(text):,}",
            reply_markup=MENU
        )
        return

    # ===== CATAT PENGELUARAN =====
    if text == "💸 Catat Pengeluaran":
        context.user_data["state"] = "EXPENSE_AMOUNT"
        await update.message.reply_text("💸 Masukkan jumlah pengeluaran:")

    elif state == "EXPENSE_AMOUNT":
        context.user_data["temp_amount"] = int(text)
        context.user_data["state"] = "EXPENSE_NOTE"
        await update.message.reply_text("📝 Keterangan pengeluaran:")

    elif state == "EXPENSE_NOTE":
        now = datetime.now()
        amount = context.user_data["temp_amount"]

        today = now.date()
        daily_limit = context.user_data.get("daily_limit")

        daily_expense = sum(
            r["amount"] for r in context.user_data["records"]
            if r["type"] == "Pengeluaran" and r["time"].date() == today
        )

        is_leak = daily_limit and (daily_expense + amount > daily_limit)

        record = {
            "time": now,
            "type": "Pengeluaran",
            "amount": amount,
            "note": text,
            "leak": is_leak
        }

        context.user_data["records"].append(record)
        context.user_data.pop("state", None)

        msg = (
            "🛑 KEBOCORAN PEMBELIAN!\n" if is_leak else "✅ Pengeluaran tercatat!\n"
        )
        msg += (
            f"🗓️ {now.strftime('%A, %d %B %Y')}\n"
            f"⏰ {now.strftime('%H:%M:%S')}\n"
            f"💰 Rp {amount:,}"
        )

        await update.message.reply_text(msg, reply_markup=MENU)

    # ===== CATAT PEMASUKAN =====
    elif text == "💰 Catat Pemasukan":
        context.user_data["state"] = "INCOME_AMOUNT"
        await update.message.reply_text("💰 Masukkan jumlah pemasukan:")

    elif state == "INCOME_AMOUNT":
        context.user_data["temp_amount"] = int(text)
        context.user_data["state"] = "INCOME_NOTE"
        await update.message.reply_text("📝 Keterangan pemasukan:")

    elif state == "INCOME_NOTE":
        now = datetime.now()
        record = {
            "time": now,
            "type": "Pemasukan",
            "amount": context.user_data["temp_amount"],
            "note": text,
            "leak": False
        }

        context.user_data["records"].append(record)
        context.user_data.pop("state", None)

        await update.message.reply_text(
            "✅ Pemasukan tercatat!\n"
            f"🗓️ {now.strftime('%A, %d %B %Y')}\n"
            f"⏰ {now.strftime('%H:%M:%S')}",
            reply_markup=MENU
        )

    # ===== RINGKASAN =====
    elif text == "📊 Ringkasan Hari Ini":
        today = datetime.now().date()

        income = sum(
            r["amount"] for r in context.user_data["records"]
            if r["type"] == "Pemasukan" and r["time"].date() == today
        )
        expense = sum(
            r["amount"] for r in context.user_data["records"]
            if r["type"] == "Pengeluaran" and r["time"].date() == today
        )

        await update.message.reply_text(
            f"📊 Ringkasan Hari Ini\n\n"
            f"💰 Pemasukan: Rp {income:,}\n"
            f"💸 Pengeluaran: Rp {expense:,}\n"
            f"📉 Selisih: Rp {income - expense:,}"
        )

    # ===== LIHAT SEMUA CATATAN =====
    elif text == "📄 Lihat Semua Catatan":
        records = context.user_data["records"]
        if not records:
            await update.message.reply_text("❗ Belum ada catatan.")
            return

        normal = [r for r in records if not r.get("leak")]
        leak = [r for r in records if r.get("leak")]

        msg = "📄 CATATAN NORMAL\n\n"
        for r in normal:
            msg += (
                f"- {r['type']} | Rp {r['amount']:,}\n"
                f"  {r['time'].strftime('%d %b %Y %H:%M')} | {r['note']}\n\n"
            )

        if leak:
            msg += "🛑 KEBOCORAN PEMBELIAN\n\n"
            for r in leak:
                msg += (
                    f"- Rp {r['amount']:,}\n"
                    f"  {r['time'].strftime('%d %b %Y %H:%M')} | {r['note']}\n\n"
                )

        await update.message.reply_text(msg)

    # ===== EXIT =====
    elif text == "❌ Exit":
        context.user_data.clear()
        await update.message.reply_text(
            "👋 Sampai jumpa bos!",
            reply_markup=ReplyKeyboardRemove()
        )

    else:
        await update.message.reply_text(
            "❓ Pakai tombol menu ya.",
            reply_markup=MENU
        )

# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot keuangan + reminder running...")
    app.run_polling()

if __name__ == "__main__":
    main()
