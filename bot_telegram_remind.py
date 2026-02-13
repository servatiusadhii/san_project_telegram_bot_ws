import os
import json
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import gspread
from google.oauth2.service_account import Credentials

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SPREADSHEET_NAME = "BOT Keuangan"

# ================= GOOGLE SHEET =================
cred_info = json.loads(os.environ["GOOGLE_CREDENTIAL_JSON"])
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_info(cred_info, scopes=SCOPES)
client = gspread.authorize(creds)
spreadsheet = client.open(SPREADSHEET_NAME)

# ================= HELPERS =================
def rupiah(n):
    return f"Rp {int(n):,}".replace(",", ".")

def now_full():
    return datetime.now().strftime("%A, %d %B %Y | %H:%M WIB")

def today():
    return datetime.now().strftime("%Y-%m-%d")

def get_user_sheet(chat_id):
    sheet_name = f"user_{chat_id}"
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=10)
        ws.append_row(["timestamp","type","amount","note","leak","saldo_sisa"])
    return ws

def get_rows_by_date(ws, date_str):
    rows = ws.get_all_records()
    return [r for r in rows if r["timestamp"].startswith(date_str)]

def get_total(ws, tipe):
    return sum(int(r["amount"]) for r in get_rows_by_date(ws, today()) if r["type"] == tipe)

def get_last_balance(ws):
    rows = ws.get_all_records()
    return int(rows[-1]["saldo_sisa"]) if rows else 0

def save_record(ws, tipe, amount, note):
    pemasukan = get_total(ws, "Pemasukan")
    pengeluaran = get_total(ws, "Pengeluaran")
    saldo = get_last_balance(ws)
    leak = "NO"

    if tipe == "Pemasukan":
        pemasukan += amount
        saldo += amount
    else:
        pengeluaran += amount
        saldo -= amount
        if pengeluaran > pemasukan:
            leak = "YES"

    ws.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        tipe, amount, note, leak, saldo
    ])
    return pemasukan, pengeluaran, saldo, leak

# ================= DAILY SUMMARY =================
async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    ws = get_user_sheet(chat_id)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    rows = get_rows_by_date(ws, yesterday)

    if not rows:
        await context.bot.send_message(chat_id, f"📭 Tidak ada transaksi kemarin ({yesterday}).")
        return

    pemasukan = sum(int(r["amount"]) for r in rows if r["type"]=="Pemasukan")
    pengeluaran = sum(int(r["amount"]) for r in rows if r["type"]=="Pengeluaran")
    sisa = pemasukan - pengeluaran
    leak_count = sum(1 for r in rows if r["leak"]=="YES")

    msg = (
        f"📅 Rekapan Keuangan Kemarin ({yesterday})\n\n"
        f"💰 Total Pemasukan : {rupiah(pemasukan)}\n"
        f"💸 Total Pengeluaran : {rupiah(pengeluaran)}\n"
        f"🧮 Sisa dana : {rupiah(sisa)}\n\n"
    )

    if leak_count > 0:
        msg += "🚨 Ada LEAK pengeluaran\n"
    if sisa < pemasukan * 0.2:
        msg += "⚠️ Sisa dana tipis\n"
    elif sisa > pemasukan * 0.5:
        msg += "👍 Keuangan stabil\n"

    msg += "\nSelamat beraktivitas 💪"
    await context.bot.send_message(chat_id, msg)

async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE):
    for ws in spreadsheet.worksheets():
        if ws.title.startswith("user_"):
            chat_id = int(ws.title.replace("user_", ""))
            await send_daily_summary(context, chat_id)

# ================= HANDLER =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["💰 Pemasukan", "💸 Pengeluaran"],
        ["📊 Summary", "📋 Catatan Hari Ini"],
        ["📈 Lihat Spreadsheet"],
    ]
    await update.message.reply_text(
        "🤖 Bot Keuangan Aktif",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    ws = get_user_sheet(chat_id)

    if text in ["💰 Pemasukan", "💸 Pengeluaran"]:
        context.user_data["type"] = "Pemasukan" if "Pemasukan" in text else "Pengeluaran"
        await update.message.reply_text("Masukkan nominal:")

    elif "type" in context.user_data and text.isdigit():
        context.user_data["amount"] = int(text)
        await update.message.reply_text("Masukkan catatan:")

    elif "amount" in context.user_data:
        loading = await update.message.reply_text("⏳ Memproses...")
        tipe = context.user_data["type"]
        amount = context.user_data["amount"]
        note = text
        pemasukan, pengeluaran, saldo, leak = save_record(ws, tipe, amount, note)
        context.user_data.clear()

        await loading.edit_text(
            f"✅ {tipe} dicatat\n"
            f"{now_full()}\n\n"
            f"{rupiah(amount)}\n"
            f"{note}\n\n"
            f"Sisa: {rupiah(pemasukan - pengeluaran)}"
        )

    elif text == "📈 Lihat Spreadsheet":
        context.user_data["awaiting_email"] = True
        await update.message.reply_text("📧 Masukkan email:")

    elif context.user_data.get("awaiting_email"):
        email = text
        spreadsheet.share(email, perm_type="user", role="writer", notify=True)
        context.user_data.clear()
        await update.message.reply_text(f"✅ Spreadsheet dibagikan ke {email}")

# ================= MAIN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # HILANGKAN CONFLICT
    app.bot.delete_webhook(drop_pending_updates=True)

    # DAILY JOB JAM 00:01
    now = datetime.now()
    target = now.replace(hour=0, minute=1, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    delay = (target - now).total_seconds()

    app.job_queue.run_repeating(daily_summary_job, interval=86400, first=delay)

    print("🤖 Bot keuangan running...")
    app.run_polling()
