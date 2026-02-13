import os, json, tempfile
from datetime import datetime, timedelta

import pandas as pd
import matplotlib.pyplot as plt

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import gspread
from google.oauth2.service_account import Credentials

# ================= CONFIG =================
BOT_TOKEN = os.environ["BOT_TOKEN"]
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

# ================= KEYBOARD =================
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["💰 Pemasukan", "💸 Pengeluaran"],
        ["📊 Summary", "📋 Catatan Hari Ini"],
        ["📊 Menu Chart", "📈 Share Spreadsheet"],
    ],
    resize_keyboard=True,
)

CHART_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📅 Chart Harian", "🗓️ Chart Bulanan"],
        ["🏷️ Top Kategori"],
        ["⬅️ Kembali"],
    ],
    resize_keyboard=True,
)

# ================= HELPERS =================
def rupiah(n):
    return f"Rp {int(n):,}".replace(",", ".")

def today():
    return datetime.now().strftime("%Y-%m-%d")

def now_full():
    return datetime.now().strftime("%d %B %Y | %H:%M WIB")

def get_user_sheet(chat_id):
    name = f"user_{chat_id}"
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=3000, cols=10)
        ws.append_row(["timestamp", "type", "amount", "note", "leak", "saldo"])
    return ws

def get_all_rows(ws):
    rows = ws.get_all_records()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["amount"] = df["amount"].astype(int)
    return df

def save_record(ws, tipe, amount, note):
    df = get_all_rows(ws)
    today_df = df[df["timestamp"].dt.strftime("%Y-%m-%d") == today()]

    pemasukan = today_df[today_df["type"] == "Pemasukan"]["amount"].sum()
    pengeluaran = today_df[today_df["type"] == "Pengeluaran"]["amount"].sum()
    saldo = int(df.iloc[-1]["saldo"]) if not df.empty else 0
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

# ================= BOROS DETECTOR =================
def detect_today_almost_boros(df):
    today_df = df[df["timestamp"].dt.strftime("%Y-%m-%d") == today()]
    pemasukan = today_df[today_df["type"] == "Pemasukan"]["amount"].sum()
    pengeluaran = today_df[today_df["type"] == "Pengeluaran"]["amount"].sum()

    if pemasukan > 0 and pengeluaran >= pemasukan * 0.8:
        return "⚠️ Pengeluaran hari ini sudah 80% dari pemasukan!"

    last7 = datetime.now() - timedelta(days=7)
    df7 = df[df["timestamp"] >= last7]
    avg = (
        df7[df7["type"] == "Pengeluaran"]
        .groupby(df7["timestamp"].dt.date)["amount"]
        .mean()
    )

    if not avg.empty and pengeluaran > avg.mean():
        return "⚠️ Pengeluaran hari ini di atas rata-rata mingguan!"

    return None

# ================= CHART =================
def save_chart(fig):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    fig.savefig(tmp.name)
    plt.close(fig)
    return tmp.name

def generate_daily_chart(df):
    last7 = datetime.now() - timedelta(days=6)
    df7 = df[df["timestamp"] >= last7]

    pivot = (
        df7.groupby([df7["timestamp"].dt.date, "type"])["amount"]
        .sum()
        .unstack(fill_value=0)
    )

    if pivot.empty:
        return None

    fig = pivot.plot(kind="bar", title="Keuangan 7 Hari Terakhir").get_figure()
    fig.tight_layout()
    return save_chart(fig)

def generate_monthly_chart(df):
    dfm = df.copy()
    dfm["date"] = dfm["timestamp"].dt.date

    pivot = (
        dfm.groupby(["date", "type"])["amount"]
        .sum()
        .unstack(fill_value=0)
    )

    if pivot.empty:
        return None

    fig = pivot.plot(title="Chart Bulanan (Harian)").get_figure()
    fig.tight_layout()
    return save_chart(fig)

def generate_top_category(df):
    out = df[df["type"] == "Pengeluaran"]
    if out.empty:
        return None, None

    top = (
        out.groupby("note")["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )

    fig = top.plot(kind="bar", title="Top 5 Kategori Pengeluaran").get_figure()
    fig.tight_layout()

    text = "🏷️ TOP KATEGORI\n\n"
    for i, (k, v) in enumerate(top.items(), 1):
        text += f"{i}. {k} — {rupiah(v)}\n"

    return save_chart(fig), text

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot Keuangan Aktif",
        reply_markup=MAIN_KEYBOARD,
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
        await update.message.reply_text("Masukkan catatan / kategori:")

    elif "amount" in context.user_data:
        tipe = context.user_data["type"]
        amount = context.user_data["amount"]
        note = text

        pemasukan, pengeluaran, saldo, leak = save_record(ws, tipe, amount, note)
        context.user_data.clear()

        msg = (
            f"✅ {tipe} dicatat\n{now_full()}\n\n"
            f"{rupiah(amount)}\n{note}\n\n"
            f"💰 {rupiah(pemasukan)}\n"
            f"💸 {rupiah(pengeluaran)}\n"
            f"🧮 Saldo {rupiah(saldo)}"
        )

        if leak == "YES":
            msg += "\n🚨 LEAK TERDETEKSI"

        await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)

        warn = detect_today_almost_boros(get_all_rows(ws))
        if warn:
            await update.message.reply_text(warn)

    elif text == "📊 Summary":
        df = get_all_rows(ws)
        today_df = df[df["timestamp"].dt.strftime("%Y-%m-%d") == today()]
        pemasukan = today_df[today_df["type"] == "Pemasukan"]["amount"].sum()
        pengeluaran = today_df[today_df["type"] == "Pengeluaran"]["amount"].sum()
        saldo = int(df.iloc[-1]["saldo"]) if not df.empty else 0

        await update.message.reply_text(
            f"📊 SUMMARY HARI INI\n\n"
            f"💰 {rupiah(pemasukan)}\n"
            f"💸 {rupiah(pengeluaran)}\n"
            f"🧮 Sisa {rupiah(pemasukan - pengeluaran)}\n"
            f"💼 Saldo {rupiah(saldo)}"
        )

    elif text == "📋 Catatan Hari Ini":
        df = get_all_rows(ws)
        today_df = df[df["timestamp"].dt.strftime("%Y-%m-%d") == today()]
        if today_df.empty:
            await update.message.reply_text("📭 Belum ada catatan hari ini.")
            return

        msg = "📋 CATATAN HARI INI\n\n"
        for _, r in today_df.iterrows():
            msg += f"{r['timestamp']} | {r['type']} | {rupiah(r['amount'])}\n"

        await update.message.reply_text(msg)

    elif text == "📈 Share Spreadsheet":
        context.user_data["awaiting_email"] = True
        await update.message.reply_text("Masukkan email Google:")

    elif context.user_data.get("awaiting_email"):
        spreadsheet.share(text, perm_type="user", role="writer", notify=True)
        context.user_data.clear()
        await update.message.reply_text("✅ Spreadsheet dibagikan", reply_markup=MAIN_KEYBOARD)

    elif text == "📊 Menu Chart":
        await update.message.reply_text("📊 Pilih chart:", reply_markup=CHART_KEYBOARD)

    elif text == "📅 Chart Harian":
        chart = generate_daily_chart(get_all_rows(ws))
        if chart:
            await update.message.reply_photo(InputFile(chart))

    elif text == "🗓️ Chart Bulanan":
        chart = generate_monthly_chart(get_all_rows(ws))
        if chart:
            await update.message.reply_photo(InputFile(chart))

    elif text == "🏷️ Top Kategori":
        chart, text_msg = generate_top_category(get_all_rows(ws))
        if chart:
            await update.message.reply_photo(InputFile(chart))
            await update.message.reply_text(text_msg)

    elif text == "⬅️ Kembali":
        await update.message.reply_text("Kembali ke menu utama", reply_markup=MAIN_KEYBOARD)

# ================= DAILY JOB =================
async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    for ws in spreadsheet.worksheets():
        if not ws.title.startswith("user_"):
            continue

        chat_id = int(ws.title.replace("user_", ""))
        df = get_all_rows(ws)
        if df.empty:
            continue

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        ydf = df[df["timestamp"].dt.strftime("%Y-%m-%d") == yesterday]
        if ydf.empty:
            continue

        pemasukan = ydf[ydf["type"] == "Pemasukan"]["amount"].sum()
        pengeluaran = ydf[ydf["type"] == "Pengeluaran"]["amount"].sum()

        await context.bot.send_message(
            chat_id,
            f"📅 Rekap {yesterday}\n\n"
            f"💰 {rupiah(pemasukan)}\n"
            f"💸 {rupiah(pengeluaran)}\n"
            f"🧮 Sisa {rupiah(pemasukan - pengeluaran)}"
        )

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    async def post_init(application: Application):
        await application.bot.delete_webhook(drop_pending_updates=True)

        now = datetime.now()
        target = now.replace(hour=0, minute=1, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        delay = (target - now).total_seconds()

        application.job_queue.run_repeating(
            daily_job, interval=86400, first=delay
        )

    app.post_init = post_init

    print("🤖 Bot keuangan running...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
