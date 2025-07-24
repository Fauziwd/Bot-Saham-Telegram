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
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, date, timedelta
import io
import json
import os
from dotenv import load_dotenv

# =============================================================================
# ⚙️ CONFIGURATION SECTION
# =============================================================================
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID_STR = os.getenv("ADMIN_TELEGRAM_ID")

ADMIN_TELEGRAM_ID = 0
if ADMIN_TELEGRAM_ID_STR and ADMIN_TELEGRAM_ID_STR.isdigit():
    ADMIN_TELEGRAM_ID = int(ADMIN_TELEGRAM_ID_STR)
else:
    print("⚠️ WARNING: ADMIN_TELEGRAM_ID tidak ditemukan atau bukan angka di file .env.")

RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
TAKE_PROFIT_PERCENTAGE = 2.0
STOP_LOSS_PERCENTAGE = 2.0
VOLUME_RATIO_THRESHOLD = 1.1
VOLUME_SPIKE_THRESHOLD = 1.5 # Threshold untuk dianggap lonjakan volume signifikan

DB_FILE = "user_database.json"

STOCK_LIST = [
    "WIFI", "CUAN", "ADRO", "SSIA", "TOBA", "DATA", "BREN", "RELI", "PGUN", "NRCA", "ARGO",
    "MERI", "BRPT", "PSAT", "CSMI", "OKAS", "PART", "PYFA", "NICL", "MINA", "EMTK", "PTPS", "MMLP",
    # Anda bisa tambahkan lebih banyak saham di sini
    "BBCA", "BBRI", "BMRI", "TLKM", "ASII", "GOTO", "UNVR", "ICBP", "MDKA", "ANTM", "INCO"
]

# =============================================================================
# 🗃️ DATABASE FUNCTIONS
# =============================================================================
def load_user_db():
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if ADMIN_TELEGRAM_ID != 0:
            admin_data = {
                str(ADMIN_TELEGRAM_ID): {
                    "first_name": "Admin", "status": "premium",
                    "requests_today": 0, "last_request_date": "2024-01-01"
                }
            }
            save_user_db(admin_data)
            return admin_data
        return {}

def save_user_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

def check_daily_limit(user_id):
    db = load_user_db()
    user = db.setdefault(str(user_id), {
        "first_name": "", "status": "free",
        "requests_today": 0, "last_request_date": str(date.today())
    })
    today_str = str(date.today())
    if user.get("last_request_date", "") != today_str:
        user["requests_today"] = 0
        user["last_request_date"] = today_str
    if user.get("status", "free") == "free":
        if user["requests_today"] >= 20: # Limit dinaikkan
            save_user_db(db)
            return False
        user["requests_today"] += 1
        save_user_db(db)
    return True

def format_price(price):
    return f"{price:,.0f}".replace(",", ".")

# =============================================================================
# 📊 ANALYSIS FUNCTIONS
# =============================================================================

def scan_volume_spikes():
    """Mencari saham dengan lonjakan volume di atas rata-rata."""
    volume_spikes = []
    for stock_code in STOCK_LIST:
        ticker = f"{stock_code}.JK"
        try:
            df = yf.download(ticker, period="2mo", progress=False, auto_adjust=False, interval="1d")
            if df.empty or len(df) < 21: continue
            df['Volume_MA20'] = df['Volume'].rolling(window=20).mean()
            last_session = df.iloc[-1]
            if pd.isna(last_session['Volume']) or pd.isna(last_session['Volume_MA20']) or last_session['Volume_MA20'] == 0: continue
            volume_ratio = last_session['Volume'] / last_session['Volume_MA20']
            if volume_ratio > VOLUME_SPIKE_THRESHOLD:
                volume_spikes.append({"stock": stock_code, "price": last_session['Close'], "volume": last_session['Volume'], "ratio": volume_ratio})
        except Exception as e:
            print(f"⚠️ Error scanning volume for {stock_code}: {str(e)}")
    return sorted(volume_spikes, key=lambda x: x['ratio'], reverse=True)

def scan_potential_stocks():
    """Mencari saham yang berpotensi naik dengan kriteria lebih longgar."""
    potential_stocks = []
    for stock_code in STOCK_LIST:
        ticker = f"{stock_code}.JK"
        try:
            df = yf.download(ticker, period="3mo", progress=False, auto_adjust=False)
            if df.empty or len(df) < 22: continue
            
            df.ta.rsi(length=14, append=True)
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df.dropna(inplace=True)
            if len(df) < 2: continue

            last = df.iloc[-1]
            prev = df.iloc[-2]

            # Kriteria Potensi Naik:
            # 1. Harga baru saja menyeberang ke atas MA20 (sinyal awal uptrend)
            cond1 = float(last['Close']) > float(last['MA20']) and float(prev['Close']) < float(prev['MA20'])
            # 2. RSI di atas 50 (momentum positif) dan belum overbought
            cond2 = 50 < float(last['RSI_14']) < RSI_OVERBOUGHT
            # 3. MA5 sedang menanjak (momentum jangka pendek)
            cond3 = float(last['MA5']) > float(prev['MA5'])

            if cond1 and cond2 and cond3:
                potential_stocks.append({
                    "stock": stock_code,
                    "price": float(last['Close']),
                    "rsi": float(last['RSI_14']),
                    "reason": "Harga tembus MA20 dengan momentum positif."
                })
        except Exception as e:
            print(f"⚠️ Error scanning potential for {stock_code}: {str(e)}")
    return potential_stocks

def analyze_stock(stock_code):
    """Menganalisis satu saham secara mendalam dan menghasilkan grafik."""
    ticker = f"{stock_code.upper()}.JK"
    try:
        df = yf.download(ticker, period="6mo", progress=False, auto_adjust=False)
        if df.empty or len(df) < 51:
            return None, "❌ Data tidak cukup untuk analisis.", None

        # --- Hitung Indikator ---
        df.ta.rsi(length=14, append=True)
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA50'] = df['Close'].rolling(window=50).mean()
        df['Volume_MA20'] = df['Volume'].rolling(window=20).mean()
        df.dropna(inplace=True)
        last = df.iloc[-1]

        # --- Buat Kesimpulan Analisis ---
        price = float(last['Close'])
        change = price - float(df.iloc[-2]['Close'])
        change_pct = (change / float(df.iloc[-2]['Close'])) * 100
        
        header = f"*{stock_code.upper()}* | Harga: `{format_price(price)}` ({change_pct:+.2f}%)\n"
        header += "━━━━━━━━━━━━━━━━━━\n"

        # Cek Posisi Harga terhadap MA
        posisi_ma = ""
        if price > last['MA5'] and price > last['MA20'] and price > last['MA50']:
            posisi_ma = "✅ Harga di atas semua MA (Strong Uptrend)."
        elif price < last['MA5'] and price < last['MA20'] and price < last['MA50']:
            posisi_ma = "❌ Harga di bawah semua MA (Strong Downtrend)."
        elif price > last['MA20'] and price < last['MA50']:
            posisi_ma = "⚠️ Harga di atas MA20, namun di bawah MA50 (Potensi Reversal/Sideways)."
        else:
            posisi_ma = "- Posisi harga mixed terhadap MA."

        # Cek RSI
        rsi_val = float(last['RSI_14'])
        posisi_rsi = ""
        if rsi_val > RSI_OVERBOUGHT:
            posisi_rsi = f"📈 RSI: `{rsi_val:.2f}` (Overbought/Jenuh Beli)."
        elif rsi_val < RSI_OVERSOLD:
            posisi_rsi = f"📉 RSI: `{rsi_val:.2f}` (Oversold/Jenuh Jual)."
        else:
            posisi_rsi = f"- RSI: `{rsi_val:.2f}` (Netral)."
            
        # Cek Volume
        vol_ratio = last['Volume'] / last['Volume_MA20']
        posisi_vol = f"- Volume: `{vol_ratio:.2f}x` dari rata-rata."

        # --- Rekomendasi ---
        rekomendasi = "💡 *Rekomendasi: TAHAN (NEUTRAL)*\n"
        alasan = "Tidak ada sinyal kuat yang terdeteksi. Sebaiknya pantau pergerakan lebih lanjut."
        if posisi_ma.startswith("✅") and 50 < rsi_val < RSI_OVERBOUGHT and vol_ratio > 1:
            rekomendasi = "🚀 *Rekomendasi: LAYAK BELI (SPECULATIVE BUY)*\n"
            alasan = "Momentum uptrend kuat didukung oleh RSI dan volume yang sehat."
        elif posisi_ma.startswith("❌") and rsi_val < 50:
            rekomendasi = "🛑 *Rekomendasi: PERTIMBANGKAN JUAL*\n"
            alasan = "Momentum downtrend kuat dan belum menunjukkan tanda pembalikan arah."
        elif rsi_val < RSI_OVERSOLD:
            rekomendasi = "💡 *Rekomendasi: PANTAU UNTUK BELI (WAIT & SEE)*\n"
            alasan = "Saham dalam kondisi jenuh jual, ada potensi technical rebound."

        summary_text = header + f"{posisi_ma}\n{posisi_rsi}\n{posisi_vol}\n\n" + rekomendasi + f"_{alasan}_"

        # --- Buat Grafik ---
        apd = [
            mpf.make_addplot(df['MA5'], color='blue', width=0.7),
            mpf.make_addplot(df['MA20'], color='orange', width=0.7),
            mpf.make_addplot(df['MA50'], color='purple', width=0.7),
        ]
        
        fig, axlist = mpf.plot(df, type='candle', style='charles',
                               title=f"\nAnalisis Teknikal {stock_code.upper()}",
                               ylabel='Harga (IDR)',
                               volume=True, ylabel_lower='Volume',
                               addplot=apd,
                               figsize=(11, 7),
                               returnfig=True)
        
        # Tambahkan legenda
        axlist[0].legend(['MA5', 'MA20', 'MA50'])
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        
        return buf, summary_text, True

    except Exception as e:
        return None, f"❌ Terjadi error saat menganalisis {stock_code}: {e}", None

def scan_signals():
    """Memindai sinyal Beli/Jual berdasarkan strategi teknikal yang ketat."""
    # Fungsi ini tetap sama, untuk sinyal yang sangat terkonfirmasi
    current_date = datetime.now().strftime('%d %b %Y')
    results = []
    buy_signals_list = []
    sell_signals_list = []

    for stock_code in STOCK_LIST:
        ticker = f"{stock_code}.JK"
        try:
            df = yf.download(ticker, period="2mo", progress=False, auto_adjust=False)
            if df.empty or len(df) < 21: continue
            df = df[~df.index.duplicated(keep='last')]
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['Volume_MA20'] = df['Volume'].rolling(window=20).mean()
            df.dropna(inplace=True)
            if len(df) < 2: continue
            last, prev = df.iloc[-1], df.iloc[-2]
            
            buy_cond1 = float(last['MA5']) > float(last['MA20']) and float(prev['MA5']) < float(prev['MA20'])
            buy_cond2 = float(last['Volume']) > (float(last['Volume_MA20']) * VOLUME_RATIO_THRESHOLD)
            buy_cond3 = float(last['Close']) > float(last['Open'])
            buy_cond4 = float(last['Close']) > float(last['MA5']) and float(last['Close']) > float(last['MA20'])
            
            sell_cond1 = float(last['MA5']) < float(last['MA20']) and float(prev['MA5']) > float(prev['MA20'])
            sell_cond2 = float(last['Volume']) > (float(last['Volume_MA20']) * VOLUME_RATIO_THRESHOLD)
            sell_cond3 = float(last['Close']) < float(last['Open'])
            sell_cond4 = float(last['Close']) < float(last['MA5']) and float(last['Close']) < float(last['MA20'])
            
            if all([buy_cond1, buy_cond2, buy_cond3, buy_cond4]):
                buy_signals_list.append(stock_code)
                harga = float(last['Close'])
                results.append({"stock": stock_code, "type": "BUY", "price": harga, "vol_ratio": float(last['Volume'])/float(last['Volume_MA20']), "entry": harga, "tp": harga * (1 + (TAKE_PROFIT_PERCENTAGE / 100)), "sl": harga * (1 - (STOP_LOSS_PERCENTAGE / 100)), "current_date": current_date})
            elif all([sell_cond1, sell_cond2, sell_cond3, sell_cond4]):
                sell_signals_list.append(stock_code)
                harga = float(last['Close'])
                results.append({"stock": stock_code, "type": "SELL", "price": harga, "vol_ratio": float(last['Volume'])/float(last['Volume_MA20']), "resistance": float(last['MA20']), "current_date": current_date})
        except Exception as e:
            print(f"⚠️ Error scanning signal for {stock_code}: {str(e)}")
    return {"results": results, "BUY": buy_signals_list, "SELL": sell_signals_list}

# =============================================================================
# 💬 TELEGRAM COMMAND HANDLERS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = load_user_db()
    if str(user.id) not in db:
        db[str(user.id)] = {"first_name": user.first_name, "status": "free"}
        save_user_db(db)
        
    welcome_message = (
        f"👋 Halo *{user.first_name}*!\n\n"
        f"Selamat datang di *Bot Analisis Saham*.\n\n"
        f"📋 **Perintah yang tersedia:**\n"
        f"• `/analisa <KODE_SAHAM>` - Analisis detail & grafik.\n"
        f"• `/potensi` - Cari saham berpotensi naik.\n"
        f"• `/volume` - Cek saham dengan lonjakan volume.\n"
        f"• `/sinyal` - Sinyal Beli/Jual (strategi ketat).\n\n"
        f"ℹ️ Ketik `/help` untuk info lebih lanjut."
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not check_daily_limit(user_id):
        await update.message.reply_text("⚠️ Batas request harian tercapai.")
        return
        
    if not context.args:
        await update.message.reply_text("Gunakan format: `/analisa <KODE_SAHAM>`\nContoh: `/analisa BBCA`")
        return

    stock_code = context.args[0]
    await update.message.reply_text(f"⏳ Menganalisis *{stock_code.upper()}*...", parse_mode='Markdown')
    
    image_buffer, summary_text, success = analyze_stock(stock_code)
    
    if success:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_buffer, caption=summary_text, parse_mode='Markdown')
    else:
        await update.message.reply_text(summary_text, parse_mode='Markdown')

async def potential_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not check_daily_limit(user_id):
        await update.message.reply_text("⚠️ Batas request harian tercapai.")
        return
    
    await update.message.reply_text("⏳ Mencari saham-saham yang berpotensi naik...", parse_mode='Markdown')
    stocks = scan_potential_stocks()
    
    if not stocks:
        await update.message.reply_text("⚠️ Tidak ditemukan saham yang menunjukkan potensi naik saat ini.")
        return
        
    text = "📈 *Saham Berpotensi Naik:*\n"
    text += "_Saham-saham ini menunjukkan sinyal awal pembalikan arah atau penguatan tren._\n\n"
    for item in stocks:
        text += (
            f"🚀 *{item['stock']}* | Harga: `{format_price(item['price'])}`\n"
            f"   └ RSI: `{item['rsi']:.2f}` | Alasan: _{item['reason']}_\n"
        )
    text += "\n_Disclaimer: Sinyal awal memiliki risiko lebih tinggi. Selalu analisa lebih dalam sebelum transaksi._"
    await update.message.reply_text(text, parse_mode='Markdown')

# --- Command handlers lama (volume & sinyal) tetap dipertahankan ---
async def volume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not check_daily_limit(user_id):
        await update.message.reply_text("⚠️ Batas request harian tercapai.")
        return
    await update.message.reply_text("⏳ Memindai lonjakan volume...", parse_mode='Markdown')
    spikes = scan_volume_spikes()
    if not spikes:
        await update.message.reply_text(f"⚠️ Tidak ada saham dengan lonjakan volume signifikan (di atas *{VOLUME_SPIKE_THRESHOLD}x* rata-rata).", parse_mode='Markdown')
        return
    text = f"📈 *Top Volume Spikes* (Data EOD/Tertunda)\n\n"
    for item in spikes[:10]:
        text += f"*{item['stock']}* | Rasio: `{item['ratio']:.2f}x` | Harga: `{format_price(item['price'])}`\n"
    text += "\n_Disclaimer: Volume tinggi bisa berarti tekanan beli atau jual. Analisa lebih lanjut._"
    await update.message.reply_text(text, parse_mode='Markdown')

async def sinyal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not check_daily_limit(user_id):
        await update.message.reply_text("⚠️ Batas request harian tercapai.")
        return
    await update.message.reply_text("⏳ Memindai sinyal (strategi ketat)...", parse_mode='Markdown')
    signals = scan_signals()
    results = signals["results"]
    if not results:
        await update.message.reply_text("⚠️ Tidak ada sinyal kuat (Golden/Death Cross) yang terkonfirmasi saat ini.")
        return
    text = "*📊 Sinyal Terkonfirmasi (Strategi Ketat):*\n"
    for item in results:
        # ... format teks sinyal tetap sama ...
        if item["type"] == "BUY":
            text += (f"\n🚀 *BUY SIGNAL: {item['stock']}*\n"
                     f"   └ Entry: `{format_price(item['entry'])}` | TP: `{format_price(item['tp'])}` | SL: `{format_price(item['sl'])}`")
        elif item["type"] == "SELL":
            text += (f"\n⚠️ *SELL SIGNAL: {item['stock']}*\n"
                     f"   └ Harga: `{format_price(item['price'])}` | Resis: `{format_price(item['resistance'])}`")
    text += f"\n\n━━━━━━━━━━━━━━━━\n✅ BUY: *{len(signals['BUY'])}* | ⚠️ SELL: *{len(signals['SELL'])}*"
    text += "\n_Sinyal ini memiliki konfirmasi kuat. Selalu DYOR._"
    await update.message.reply_text(text, parse_mode='Markdown')

async def handle_unknown_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Perintah tidak dikenali. Ketik /start atau /help.")

# =============================================================================
# 🚀 MAIN APPLICATION
# =============================================================================
def main():
    print("🚀 Bot Analisis Saham sedang dimulai...")
    if not TELEGRAM_BOT_TOKEN:
        print("!!! FATAL ERROR: TELEGRAM_BOT_TOKEN tidak ditemukan di file .env !!!")
        return
    if ADMIN_TELEGRAM_ID == 0:
        print("!!! FATAL ERROR: ADMIN_TELEGRAM_ID tidak ditemukan di file .env !!!")
        return

    load_user_db()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Daftarkan semua command handler
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("analisa", analyze_command))
    application.add_handler(CommandHandler("potensi", potential_command))
    application.add_handler(CommandHandler("volume", volume_command))
    application.add_handler(CommandHandler("sinyal", sinyal_command))
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown_commands))
    
    print(f"✅ Bot berhasil terhubung. Admin ID: {ADMIN_TELEGRAM_ID}. Siap menerima perintah.")
    application.run_polling()

if __name__ == '__main__':
    main()
