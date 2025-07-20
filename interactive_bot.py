# -*- coding: utf-8 -*-
"""
📈 IDX Stock Analysis Bot for Telegram
🔍 Technical Scanner with BUY/SELL Signals
🛠️ Powered by yfinance, pandas_ta, mplfinance
"""

# =============================================================================
# 🧩 IMPORT LIBRARIES
# =============================================================================
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import mplfinance as mpf
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, date
import io
import json
import os                    # <-- TAMBAHKAN: Untuk mengakses environment variables
from dotenv import load_dotenv # <-- TAMBAHKAN: Untuk memuat file .env

# =============================================================================
# ⚙️ CONFIGURATION SECTION
# =============================================================================
load_dotenv() # <-- TAMBAHKAN: Memuat variabel dari file .env ke environment

# --- Ambil variabel rahasia dari environment ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID_STR = os.getenv("ADMIN_TELEGRAM_ID")

# --- Konversi ADMIN_TELEGRAM_ID ke integer dengan penanganan error ---
ADMIN_TELEGRAM_ID = 0 # Default value jika tidak ada
if ADMIN_TELEGRAM_ID_STR and ADMIN_TELEGRAM_ID_STR.isdigit():
    ADMIN_TELEGRAM_ID = int(ADMIN_TELEGRAM_ID_STR)
else:
    print("⚠️ WARNING: ADMIN_TELEGRAM_ID tidak ditemukan atau bukan angka di file .env.")


# --- Konfigurasi yang tidak rahasia bisa tetap di sini ---
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
TAKE_PROFIT_PERCENTAGE = 2.0
STOP_LOSS_PERCENTAGE = 2.0
VOLUME_RATIO_THRESHOLD = 1.1

DB_FILE = "user_database.json"

STOCK_LIST = [
    "SSIA", "BWPT", "ADRO", "WIFI", "BOLA", "RELI", "OKAS", "TOBA", "INET", "IOTF", "TEBE",
    "CUAN", "BRPT", "BLOG", "PSAT", "PGAS", "SHID", "PYFA", "BREN", "SOTS", "NICL", "ARCI", "PEGE"
]

# =============================================================================
# 🗃️ DATABASE FUNCTIONS
# =============================================================================
def load_user_db():
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Pastikan ADMIN_TELEGRAM_ID sudah terisi sebelum membuat DB
        if ADMIN_TELEGRAM_ID != 0:
            admin_data = {
                str(ADMIN_TELEGRAM_ID): {
                    "first_name": "Admin",
                    "status": "premium",
                    "requests_today": 0,
                    "last_request_date": "2024-01-01"
                }
            }
            save_user_db(admin_data)
            return admin_data
        return {} # Kembalikan dictionary kosong jika admin ID belum ada

def save_user_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

# ... (Sisa fungsi Anda seperti check_daily_limit, format_price, scan_signals tidak perlu diubah) ...
# NOTE: Pastikan semua fungsi lainnya tetap sama seperti kode asli Anda.
# Saya hanya akan menyertakan fungsi yang relevan dengan perubahan.

def check_daily_limit(user_id):
    db = load_user_db()
    user = db.setdefault(str(user_id), {
        "first_name": "",
        "status": "free",
        "requests_today": 0,
        "last_request_date": str(date.today())
    })
    today_str = str(date.today())
    if user.get("last_request_date", "") != today_str:
        user["requests_today"] = 0
        user["last_request_date"] = today_str
    if user.get("status", "free") == "free":
        if user["requests_today"] >= 10:
            save_user_db(db)
            return False
        user["requests_today"] += 1
        save_user_db(db)
    return True

def format_price(price):
    return f"{price:,.0f}".replace(",", ".")

def scan_signals():
    current_date = datetime.now().strftime('%d %b %Y')
    buy_signals = []
    sell_signals = []
    results = []
    for stock_code in STOCK_LIST:
        ticker = f"{stock_code}.JK"
        try:
            df = yf.download(ticker, period="2mo", progress=False, auto_adjust=False)
            df = df[~df.index.duplicated(keep='last')]
            if len(df) < 21:
                continue
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['Volume_MA20'] = df['Volume'].rolling(window=20).mean()
            last = df.iloc[-1]
            prev = df.iloc[-2]
            indikator_list = [
                last['MA5'], last['MA20'], last['Volume_MA20'],
                prev['MA5'], prev['MA20'], last['Close'], last['Open'], last['Volume']
            ]
            if any(pd.isna(indikator_list)):
                continue
            buy_cond1 = (float(last['MA5']) > float(last['MA20'])) and (float(prev['MA5']) < float(prev['MA20']))
            buy_cond2 = float(last['Volume']) > (float(last['Volume_MA20']) * VOLUME_RATIO_THRESHOLD)
            buy_cond3 = float(last['Close']) > float(last['Open'])
            buy_cond4 = (float(last['Close']) > float(last['MA5'])) and (float(last['Close']) > float(last['MA20']))
            sell_cond1 = (float(last['MA5']) < float(last['MA20'])) and (float(prev['MA5']) > float(prev['MA20']))
            sell_cond2 = float(last['Volume']) > (float(last['Volume_MA20']) * VOLUME_RATIO_THRESHOLD)
            sell_cond3 = float(last['Close']) < float(last['Open'])
            sell_cond4 = (float(last['Close']) < float(last['MA5'])) and (float(last['Close']) < float(last['MA20']))
            if buy_cond1 and buy_cond2 and buy_cond3 and buy_cond4:
                buy_signals.append(stock_code)
                harga = float(last['Close'])
                vol_ratio = float(last['Volume']) / float(last['Volume_MA20'])
                ma5, ma20 = float(last['MA5']), float(last['MA20'])
                results.append({
                    "stock": stock_code, "type": "BUY", "price": harga,
                    "vol_ratio": vol_ratio, "ma5": ma5, "ma20": ma20,
                    "entry": harga, "tp": harga * (1 + (TAKE_PROFIT_PERCENTAGE / 100)),
                    "sl": harga * (1 - (STOP_LOSS_PERCENTAGE / 100)),
                    "current_date": current_date
                })
            elif sell_cond1 and sell_cond2 and sell_cond3 and sell_cond4:
                sell_signals.append(stock_code)
                harga = float(last['Close'])
                vol_ratio = float(last['Volume']) / float(last['Volume_MA20'])
                ma5, ma20 = float(last['MA5']), float(last['MA20'])
                results.append({
                    "stock": stock_code, "type": "SELL", "price": harga,
                    "vol_ratio": vol_ratio, "ma5": ma5, "ma20": ma20,
                    "resistance": ma20, "current_date": current_date
                })
        except Exception as e:
            print(f"⚠️ Error scanning {stock_code}: {str(e)}")
    return results, buy_signals, sell_signals

# =============================================================================
# 💬 TELEGRAM COMMAND HANDLERS
# =============================================================================
async def sinyal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not check_daily_limit(user_id):
        await update.message.reply_text(
            "⚠️ Anda telah mencapai batas maksimal (10) analisis hari ini untuk akun gratis. "
            "Silakan tunggu besok."
        )
        return
    await update.message.reply_text("⏳ Memindai sinyal BUY/SELL pada saham trending/top gainer ...", parse_mode='Markdown')
    results, buy_signals, sell_signals = scan_signals()
    if not results:
        await update.message.reply_text("⚠️ Tidak ada sinyal BUY/SELL ditemukan saat ini.")
        return
    text = "*📊 Sinyal Harian Saham Trending/Top Gainer:*\n"
    for item in results:
        if item["type"] == "BUY":
            text += (
                f"\n🚀 *BUY SIGNAL: {item['stock']}* ({item['current_date']})\n"
                f"   💵 Harga: `{format_price(item['price'])}`\n"
                f"   📈 Volume Ratio: `{item['vol_ratio']:.2f}x`\n"
                f"   📊 MA5: `{item['ma5']:.2f}` | MA20: `{item['ma20']:.2f}`\n"
                f"   🎯 Entry: `{format_price(item['entry'])}`\n"
                f"   ✅ Take Profit ({TAKE_PROFIT_PERCENTAGE}%): `{format_price(item['tp'])}`\n"
                f"   ❌ Stop Loss ({STOP_LOSS_PERCENTAGE}%): `{format_price(item['sl'])}`\n"
                f"   #GoldenCross #{item['stock']}\n"
            )
        elif item["type"] == "SELL":
            text += (
                f"\n⚠️ *SELL SIGNAL: {item['stock']}* ({item['current_date']})\n"
                f"   💵 Harga: `{format_price(item['price'])}`\n"
                f"   📈 Volume Ratio: `{item['vol_ratio']:.2f}x`\n"
                f"   📊 MA5: `{item['ma5']:.2f}` | MA20: `{item['ma20']:.2f}`\n"
                f"   🛑 Resistance: `{format_price(item['resistance'])}`\n"
                f"   #DeathCross #{item['stock']}\n"
            )
    text += f"\n━━━━━━━━━━━━━━━━\n✅ BUY signals: *{len(buy_signals)}* | ⚠️ SELL signals: *{len(sell_signals)}*"
    text += "\n_Disclaimer: Sinyal berdasarkan indikator teknikal sederhana. Selalu DYOR & gunakan manajemen risiko!_"
    await update.message.reply_text(text, parse_mode='Markdown')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    db = load_user_db()
    if user_id not in db:
        db[user_id] = {
            "first_name": user.first_name,
            "status": "free",
        }
        save_user_db(db)
    welcome_message = (
        f"👋 Halo *{user.first_name}*!\n\n"
        f"Selamat datang di *Bot Cuan Maksimal!*.\n\n"
        f"📋 **Perintah yang tersedia:**\n"
        f"• `/analisa <KODE_SAHAM>` - Analisis harian\n"
        f"• `/weekly <KODE_SAHAM>` - Analisis mingguan\n"
        f"• `/sinyal` - Sinyal BUY/SELL saham tren\n\n"
        f"ℹ️ Ketik `/help` untuk info lebih lanjut."
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fitur analisa belum diimplementasi dan masih dalam tahap pengembangan oleh Admin.")

async def weekly_analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fitur analisa mingguan belum diimplementasi dan masih dalam tahap pengembangan oleh Admin.")

async def handle_unknown_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Maaf, saya tidak mengerti perintah itu. Silakan gunakan /help untuk melihat daftar perintah. \ngosa ngide cik 🗿")

# =============================================================================
# 🚀 MAIN APPLICATION
# =============================================================================
def main():
    print("🚀 Bot Analisis Saham sedang dimulai...")
    # <-- UBAH: Pemeriksaan token yang lebih baik
    if not TELEGRAM_BOT_TOKEN:
        print("!!! FATAL ERROR: TELEGRAM_BOT_TOKEN tidak ditemukan di file .env !!!")
        print("Pastikan Anda sudah membuat file .env dan mengisinya dengan benar.")
        return # Hentikan program jika token tidak ada

    if ADMIN_TELEGRAM_ID == 0:
        print("!!! FATAL ERROR: ADMIN_TELEGRAM_ID tidak ditemukan di file .env !!!")
        return

    load_user_db()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("analisa", analyze_command))
    application.add_handler(CommandHandler("weekly", weekly_analyze_command))
    application.add_handler(CommandHandler("sinyal", sinyal_command))
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown_commands))
    
    print(f"✅ Bot berhasil terhubung. Admin ID: {ADMIN_TELEGRAM_ID}. Siap menerima perintah.")
    application.run_polling()

if __name__ == '__main__':
    main()
