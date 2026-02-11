import os
import json
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

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
bot = Bot(BOT_TOKEN)

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

    ws.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tipe, amount, note, leak, saldo])
    return pemasukan, pengeluaran, saldo, leak

# ================= DAILY SUMMARY =================
def send_daily_summary(chat_id):
    ws = get_user_sheet(chat_id)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    rows = get_rows_by_date(ws, yesterday)

    if not rows:
        bot.send_message(chat_id, f"📭 Tidak ada transaksi kemarin ({yesterday}).")
        return

    pemasukan = sum(int(r["amount"]) for r in rows if r["type"]=="Pemasukan")
    pengeluaran = sum(int(r["amount"]) for r in rows if r["type"]=="Pengeluaran")
    sisa = pemasukan - pengeluaran
    leak_count = sum(1 for r in rows if r["leak"]=="YES")

    msg = f"📅 Rekapan Keuangan Kemarin ({yesterday})\n\n"
    msg += f"💰 Total Pemasukan : {rupiah(pemasukan)}\n"
    msg += f"💸 Total Pengeluaran : {rupiah(pengeluaran)}\n"
    msg += f"🧮 Sisa dana : {rupiah(sisa)}\n\n"

    if leak_count > 0:
        msg += "🚨 Ada pengeluaran melebihi pemasukan (LEAK)\n"

    if sisa < pemasukan * 0.2:
        msg += "⚠️ Hati-hati! Sisa dana tipis, jangan boros hari ini.\n"
    elif sisa > pemasukan * 0.5:
        msg += "👍 Kondisi keuangan stabil. Bisa rencanakan tabungan/investasi.\n"

    msg += "\nSelamat beraktivitas hari ini! 💪"
    bot.send_message(chat_id, msg)

def send_all_users_summary():
    for ws in spreadsheet.worksheets():
        if ws.title.startswith("user_"):
            chat_id = int(ws.title.replace("user_", ""))
            send_daily_summary(chat_id)

# ================= HANDLER BOT =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["💰 Pemasukan", "💸 Pengeluaran"],
        ["📊 Summary", "📋 Catatan Hari Ini"],
        ["📈 Lihat Spreadsheet"],
    ]
    await update.message.reply_text(
        "🤖 Bot Keuangan Aktif\nKelola keuangan harianmu dengan rapi 💸",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    ws = get_user_sheet(chat_id)

    # ================= INPUT HARIAN =================
    if text in ["💰 Pemasukan", "💸 Pengeluaran"]:
        context.user_data["type"] = "Pemasukan" if "Pemasukan" in text else "Pengeluaran"
        await update.message.reply_text("Masukkan nominal transaksi:")

    elif "type" in context.user_data and text.isdigit():
        context.user_data["amount"] = int(text)
        await update.message.reply_text("Tambahkan catatan transaksi:")

    elif "amount" in context.user_data:
        loading = await update.message.reply_text("⏳ Sedang memproses...")
        tipe = context.user_data["type"]
        amount = context.user_data["amount"]
        note = text
        pemasukan, pengeluaran, saldo, leak = save_record(ws, tipe, amount, note)
        sisa = pemasukan - pengeluaran
        context.user_data.clear()

        msg = (
            f"✅ {tipe} berhasil dicatat\n\n"
            f"🗓️ {now_full()}\n\n"
            f"Nominal : {rupiah(amount)}\n"
            f"Catatan : {note}\n\n"
            f"📊 Ringkasan Hari Ini\n"
            f"• Pemasukan : {rupiah(pemasukan)}\n"
            f"• Pengeluaran : {rupiah(pengeluaran)}\n"
            f"• Sisa dana : {rupiah(sisa)}\n"
        )
        if pemasukan > 0 and sisa <= pemasukan * 0.2 and leak=="NO":
            msg += "\n⚠️ Sisa dana hari ini tinggal 20%."
        if leak=="YES":
            msg += "\n🚨 LEAK! Pengeluaran melebihi pemasukan."

        await loading.edit_text(msg)

    # ================= MENU =================
    elif text == "📊 Summary":
        loading = await update.message.reply_text("⏳ Sedang memproses...")
        pemasukan = get_total(ws, "Pemasukan")
        pengeluaran = get_total(ws, "Pengeluaran")
        saldo = get_last_balance(ws)
        await loading.edit_text(
            f"📊 SUMMARY HARI INI\n\n"
            f"🗓️ {now_full()}\n"
            f"💰 Pemasukan : {rupiah(pemasukan)}\n"
            f"💸 Pengeluaran : {rupiah(pengeluaran)}\n"
            f"🧮 Sisa dana : {rupiah(pemasukan - pengeluaran)}\n"
            f"💼 Saldo total : {rupiah(saldo)}"
        )

    elif text == "📋 Catatan Hari Ini":
        loading = await update.message.reply_text("⏳ Sedang memproses...")
        data = get_rows_by_date(ws, today())
        if not data:
            await loading.edit_text("📭 Belum ada catatan hari ini.")
            return
        msg = "📋 CATATAN HARI INI\n\n"
        for r in data:
            msg += (
                f"{r['timestamp']}\n"
                f"{r['type']} | {rupiah(r['amount'])}\n"
                f"Sisa : {rupiah(r['saldo_sisa'])}\n"
                f"Leak : {r['leak']}\n\n"
            )
        await loading.edit_text(msg)

    elif text == "📈 Lihat Spreadsheet":
        await update.message.reply_text("📧 Masukkan email untuk dibagikan akses spreadsheet:")
        context.user_data["awaiting_email"] = True
    elif "awaiting_email" in context.user_data:
        email = text
        ws.share(email, perm_type='user', role='writer', notify=True)
        await update.message.reply_text(f"✅ Spreadsheet telah dibagikan ke {email}")
        context.user_data.clear()

# ================= MAIN =================
if __name__ == "__main__":
    import sys

    if "--daily-summary" in sys.argv:
        send_all_users_summary()
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        # ===== DAILY SUMMARY JOB QUEUE =====
        async def send_all_users_summary_job(context):
            try:
                print(f"📬 Mengirim daily summary ke semua user ({datetime.now()})")
                send_all_users_summary()
            except Exception as e:
                print(f"❌ Error saat daily summary: {e}")

        job_queue = app.job_queue

        # hitung detik sampai jam 00:01
        now = datetime.now()
        target = now.replace(hour=0, minute=1, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        delay_seconds = (target - now).total_seconds()

        # jalankan job tiap 24 jam, mulai dari delay_seconds
        job_queue.run_repeating(send_all_users_summary_job, interval=86400, first=delay_seconds)

        print("🤖 Bot keuangan running...")
        app.run_polling()
