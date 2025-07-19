import pandas as pd
import yfinance as yf
import requests
import time
from datetime import datetime

# ==============================================================================
# --- BAGIAN KONFIGURASI (SILAKAN DIUBAH SESUAI KEBUTUHAN) ---
# ==============================================================================
# 1. Konfigurasi Telegram Anda
TELEGRAM_BOT_TOKEN = '8037524581:AAFxuJh77ZFi0YTaFgRdZ7KjaHZGLSLVPkY'
TELEGRAM_CHAT_ID = '-1002777975408'

# 2. Daftar Saham yang Ingin Dipantau
STOCK_LIST = ['SSIA.JK', 'BWPT.JK', 'ADRO.JK', 'WIFI.JK', 'BOLA.JK', 'RELI.JK', 
              'OKAS.JK', 'TOBA.JK', 'INET.JK', 'IOTF.JK', 'TEBE.JK', 'CUAN.JK', 
              'BRPT.JK', 'BLOG.JK', 'PSAT.JK', 'PGAS.JK', 'SHID.JK', 'PYFA.JK',
              'BREN.JK', 'SOTS.JK', 'NICL.JK', 'ARCI.JK', 'PEGE.JK']

# 3. Parameter Strategi
VOLUME_RATIO_THRESHOLD = 1.1 
TAKE_PROFIT_PERCENTAGE = 2.0
STOP_LOSS_PERCENTAGE = 2.0

# --- BATAS KONFIGURASI ---

def send_telegram_message(message):
    """Fungsi untuk mengirim pesan ke Telegram dengan format Markdown."""
    api_url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    try:
        requests.post(api_url, json={
            'chat_id': TELEGRAM_CHAT_ID, 
            'text': message, 
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True
        })
    except Exception as e:
        print(f"Gagal mengirim pesan: {e}")

def format_price(price):
    """Format harga dengan pemisah ribuan."""
    return f"{price:,.0f}".replace(",", ".")

def scan_stocks():
    """Fungsi utama untuk memindai saham dan mencari sinyal."""
    print("Memulai pemindaian saham harian (BUY & SELL)...")
    current_date = datetime.now().strftime('%d %b %Y')
    found_buy_signals = 0
    found_sell_signals = 0
    
    for stock_code in STOCK_LIST:
        try:
            print(f"\n---> Menganalisis {stock_code}...")
            # Ambil data historis 2 bulan terakhir
            df = yf.download(stock_code, period="2mo", progress=False, auto_adjust=False)
            df = df[~df.index.duplicated(keep='last')]

            if len(df) < 21:
                print(f"  -> Data tidak cukup untuk {stock_code}.")
                continue

            # Hitung indikator teknikal
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['Volume_MA20'] = df['Volume'].rolling(window=20).mean()

            last = df.iloc[-1]  # Data hari terakhir
            prev = df.iloc[-2]  # Data hari sebelumnya
            
            # Cek kelengkapan data
            indikator_list = [
                last['MA5'], last['MA20'], last['Volume_MA20'], 
                prev['MA5'], prev['MA20'], last['Close'], last['Open'], last['Volume']
            ]
            if any(pd.isna(indikator_list)):
                 print(f"  -> Data indikator tidak lengkap, melewati {stock_code}.")
                 continue

            # --- Mengecek Kondisi Sinyal BUY (Golden Cross) ---
            try:
                buy_cond1 = (float(last['MA5']) > float(last['MA20'])) and (float(prev['MA5']) < float(prev['MA20']))
                buy_cond2 = float(last['Volume']) > (float(last['Volume_MA20']) * VOLUME_RATIO_THRESHOLD)
                buy_cond3 = float(last['Close']) > float(last['Open'])
                buy_cond4 = (float(last['Close']) > float(last['MA5'])) and (float(last['Close']) > float(last['MA20']))
            except Exception as e:
                print(f"  -> Error logika kondisi BUY: {e}")
                continue

            # --- Mengecek Kondisi Sinyal SELL (Death Cross) ---
            try:
                sell_cond1 = (float(last['MA5']) < float(last['MA20'])) and (float(prev['MA5']) > float(prev['MA20']))
                sell_cond2 = float(last['Volume']) > (float(last['Volume_MA20']) * VOLUME_RATIO_THRESHOLD)
                sell_cond3 = float(last['Close']) < float(last['Open'])
                sell_cond4 = (float(last['Close']) < float(last['MA5'])) and (float(last['Close']) < float(last['MA20']))
            except Exception as e:
                print(f"  -> Error logika kondisi SELL: {e}")
                continue

            if buy_cond1 and buy_cond2 and buy_cond3 and buy_cond4:
                print(f"✅✅✅ SINYAL BUY DITEMUKAN untuk {stock_code}!")
                found_buy_signals += 1
                harga = float(last['Close'])
                vol_ratio = float(last['Volume']) / float(last['Volume_MA20'])
                ma5, ma20 = float(last['MA5']), float(last['MA20'])
                support, entry = ma20, harga
                tp = harga * (1 + (TAKE_PROFIT_PERCENTAGE / 100))
                sl = harga * (1 - (STOP_LOSS_PERCENTAGE / 100))
                
                # Format pesan BUY dengan visual yang ditingkatkan
                message = (
                    f"🚀 *BUY SIGNAL ALERT* 🚀\n"
                    f"📈 *{stock_code}* | {current_date}\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"💰 *Price*: `{format_price(harga)}`\n"
                    f"📊 *Volume Ratio*: `{vol_ratio:.2f}x` (20-day avg)\n"
                    f"📉 *Moving Averages*:\n"
                    f"   - MA5: `{ma5:,.2f}`\n"
                    f"   - MA20: `{ma20:,.2f}`\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"🎯 *Trade Setup*:\n"
                    f"   - Entry: `{format_price(entry)}`\n"
                    f"   - Support: `{format_price(support)}`\n"
                    f"   - Take Profit ({TAKE_PROFIT_PERCENTAGE}%): `{format_price(tp)}`\n"
                    f"   - Stop Loss ({STOP_LOSS_PERCENTAGE}%): `{format_price(sl)}`\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"🔍 *Signal Confirmation*:\n"
                    f"   ✔ Golden Cross (MA5 > MA20)\n"
                    f"   ✔ Volume Spike ({vol_ratio:.2f}x average)\n"
                    f"   ✔ Bullish Candle (Close > Open)\n"
                    f"\n#BuySignal #GoldenCross #{stock_code.split('.')[0]}"
                )
                send_telegram_message(message)
                time.sleep(1)
            
            elif sell_cond1 and sell_cond2 and sell_cond3 and sell_cond4:
                print(f"⚠️⚠️⚠️ SINYAL SELL DITEMUKAN untuk {stock_code}!")
                found_sell_signals += 1
                harga = float(last['Close'])
                vol_ratio = float(last['Volume']) / float(last['Volume_MA20'])
                ma5, ma20 = float(last['MA5']), float(last['MA20'])
                resistance = ma20
                
                # Format pesan SELL dengan visual yang ditingkatkan
                message = (
                    f"⚠️ *SELL SIGNAL WARNING* ⚠️\n"
                    f"📉 *{stock_code}* | {current_date}\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"💰 *Price*: `{format_price(harga)}`\n"
                    f"📊 *Volume Ratio*: `{vol_ratio:.2f}x` (20-day avg)\n"
                    f"📉 *Moving Averages*:\n"
                    f"   - MA5: `{ma5:,.2f}`\n"
                    f"   - MA20: `{ma20:,.2f}`\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"🚨 *Warning Signs*:\n"
                    f"   ✖ Death Cross (MA5 < MA20)\n"
                    f"   ✖ Volume Spike ({vol_ratio:.2f}x average)\n"
                    f"   ✖ Bearish Candle (Close < Open)\n"
                    f"   ✖ Resistance at: `{format_price(resistance)}`\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"💡 *Recommendation*:\n"
                    f"   Consider taking profits or tightening stop-loss\n"
                    f"   Potential downside target: `{format_price(harga * 0.95)}` (-5%)\n"
                    f"\n#SellSignal #Warning #{stock_code.split('.')[0]}"
                )
                send_telegram_message(message)
                time.sleep(1)

            else:
                print(f"  -> Tidak ada sinyal signifikan untuk {stock_code}.")

        except Exception as e:
            print(f"Error tidak terduga saat menganalisis {stock_code}: {e}")
            
    print(f"\n--- Pemindaian Selesai. Sinyal BUY: {found_buy_signals}, Sinyal SELL: {found_sell_signals} ---")
    
    # Format pesan ringkasan akhir
    final_message = (
        f"📊 *DAILY SCAN COMPLETE* 📊\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📅 *Date*: {current_date}\n"
        f"🔄 *Stocks analyzed*: {len(STOCK_LIST)}\n"
        f"✅ *BUY signals found*: *{found_buy_signals}*\n"
        f"⚠️ *SELL signals found*: *{found_sell_signals}*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⏳ *Next scan* in 24 hours\n"
        f"#MarketScan #TradingSignals #StockAnalysis"
    )
    send_telegram_message(final_message)
    print("Notifikasi akhir telah dikirim ke Telegram.")

if __name__ == '__main__':
    scan_stocks()