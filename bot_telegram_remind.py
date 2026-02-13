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

import pandas as pd
import matplotlib.pyplot as plt
import tempfile

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
    name = f"user_{chat_id}"
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=1000, cols=10)
        ws.append_row(["timestamp","type","amount","note","leak","saldo_sisa"])
    return ws

def get_rows_by_date(ws, date_str):
    return [r for r in ws.get_all_records() if r["timestamp"].startswith(date_str)]

def get_total_today(ws, tipe):
    return sum(int(r["amount"]) for r in get_rows_by_date(ws, today()) if r["type"] == tipe)

def get_last_balance(ws):
    rows = ws.get_all_records()
    return int(rows[-1]["saldo_sisa"]) if rows else 0

def save_record(ws, tipe, amount, note):
    pemasukan = get_total_today(ws, "Pemasukan")
    pengeluaran = get_total_today(ws, "Pengeluaran")
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

# ================= CHART 7 HARI =================
def generate_7_days_chart(ws):
    rows = ws.get_all_records()
    if not rows:
        return None

    df = pd.DataFrame(rows)
    if df.empty:
        return None

    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    last_7 = datetime.now().date() - timedelta(days=6)
    df = df[df["date"] >= last_7]

    if df.empty:
        return None

    inc = df[df["type"]=="Pemasukan"].groupby("date")["amount"].sum()
    exp = df[df["type"]=="Pengeluaran"].groupby("date")["amount"].sum()

    plt.figure()
    inc.plot(marker="o", label="Pemasukan")
    exp.plot(marker="o", label="Pengeluaran")
    plt.title("Grafik Keuangan 7 Hari")
    plt.xlabel("Tanggal")
    plt.ylabel("Rupiah")
    plt.legend()
    plt.tight_layout()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    plt.savefig(tmp.name)
    plt.close()
    return tmp.name

# ================= WEEKLY CHECK =================
def get_week_total(ws, start, end):
    total = 0
    for r in ws.get_all_records():
        d = datetime.strptime(r["timestamp"][:10], "%Y-%m-%d").date()
        if start <= d <= end and r["type"] == "Pengeluaran":
            total += int(r["amount"])
    return total

# ================= DAILY SUMMARY =================
async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    ws = get_user_sheet(chat_id)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    rows = get_rows_by_date(ws, yesterday)

    if not rows:
        await context.bot.send_message(chat_id, f"📭 Tidak ada transaksi kemarin ({yesterday})")
        return

    pemasukan = sum(int(r["amount"]) for r in rows if r["type"]=="Pemasukan")
    pengeluaran = sum(int(r["amount"]) for r in rows if r["type"]=="Pengeluaran")
    sisa = pemasukan - pengeluaran
    leak_count = sum(1 for r in rows if r["leak"]=="YES")

    msg = (
        f"📅 Rekapan Keuangan Kemarin ({yesterday})\n\n"
        f"💰 Pemasukan : {rupiah(pemasukan)}\n"
        f"💸 Pengeluaran : {rupiah(pengeluaran)}\n"
        f"🧮 Sisa dana : {rupiah(sisa)}\n\n"
    )

    if leak_count:
        msg += "🚨 Ada pengeluaran melebihi pemasukan\n"
    if sisa < pemasukan * 0.2:
        msg += "⚠️ Sisa dana tipis\n"
    elif sisa > pemasukan * 0.5:
        msg += "👍 Kondisi keuangan stabil\n"

    await context.bot.send_message(chat_id, msg)

async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE):
    for ws in spreadsheet.worksheets():
        if ws.title.startswith("user_"):
            await send_daily_summary(context, int(ws.title.replace("user_", "")))

# ================= WEEKLY JOB =================
async def weekly_spending_job(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().date()
    start_this = today - timedelta(days=today.weekday())
    end_this = start_this + timedelta(days=6)
    start_last = start_this - timedelta(days=7)
    end_last = start_last + timedelta(days=6)

    for ws in spreadsheet.worksheets():
        if not ws.title.startswith("user_"):
            continue

        chat_id = int(ws.title.replace("user_", ""))
        this_week = get_week_total(ws, start_this, end_this)
        last_week = get_week_total(ws, start_last, end_last)

        if last_week > 0 and this_week > last_week * 1.3:
            await context.bot.send_message(
                chat_id,
                f"🚨 PERINGATAN BOROS\n\n"
                f"Minggu lalu : {rupiah(last_week)}\n"
                f"Minggu ini : {rupiah(this_week)}\n\n"
                f"Coba evaluasi pengeluaranmu 👀"
            )

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["💰 Pemasukan", "💸 Pengeluaran"],
        ["📊 Summary", "📋 Catatan Hari Ini"],
        ["📊 Chart 7 Hari"],
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
            f"✅ {tipe} dicatat\n\n"
            f"{now_full()}\n"
            f"{rupiah(amount)}\n{note}\n\n"
            f"Sisa hari ini: {rupiah(pemasukan - pengeluaran)}"
        )

    elif text == "📊 Chart 7 Hari":
        chart = generate_7_days_chart(ws)
        if not chart:
            await update.message.reply_text("📭 Data belum cukup untuk chart.")
            return
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=open(chart, "rb"),
            caption="📊 Grafik 7 hari terakhir"
        )

    elif text == "📈 Lihat Spreadsheet":
        context.user_data["awaiting_email"] = True
        await update.message.reply_text("📧 Masukkan email:")

    elif context.user_data.get("awaiting_email"):
        spreadsheet.share(text, perm_type="user", role="writer", notify=True)
        context.user_data.clear()
        await update.message.reply_text(f"✅ Spreadsheet dibagikan ke {text}")

# ================= MAIN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # anti conflict
    app.bot.delete_webhook(drop_pending_updates=True)

    # DAILY 00:01
    now = datetime.now()
    target = now.replace(hour=0, minute=1, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)

    app.job_queue.run_repeating(
        daily_summary_job,
        interval=86400,
        first=(target - now).total_seconds()
    )

    # WEEKLY MONDAY 08:00
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    while target.weekday() != 0:
        target += timedelta(days=1)

    app.job_queue.run_repeating(
        weekly_spending_job,
        interval=7*86400,
        first=(target - now).total_seconds()
    )

    print("🤖 Bot keuangan running...")
    app.run_polling()
