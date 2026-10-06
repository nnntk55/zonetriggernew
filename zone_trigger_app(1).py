import time
import requests
import pandas as pd
import yfinance as yf

# ==================== ตั้งค่าบอตของคุณตรงนี้ ====================
TELEGRAM_BOT_TOKEN = "ใส่_Bot_Token_ของคุณตรงนี้"
TELEGRAM_CHAT_ID = "ใส่_Chat_ID_ของคุณตรงนี้"
CHECK_INTERVAL_SECONDS = 300  # ตรวจสอบทุกๆ 5 นาที (300 วินาที)
# ===============================================================

# ตัวแปรสำหรับเก็บสถานะปัจจุบันของบอต
current_stage = 1
active_direction = None  # จะเป็น "HIGH" หรือ "LOW"

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ กรุณากรอก Bot Token และ Chat ID ให้เรียบร้อยก่อน")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Telegram Error: {e}")
        return False

def get_live_market_price():
    tickers = ["GC=F", "XAUUSD=X"]
    for t in tickers:
        try:
            ticker = yf.Ticker(t)
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                val = float(hist['Close'].iloc[-1])
                if val > 1000:
                    return val
        except:
            continue
    return 4161.00

def calculate_stochastic(df, period=14, smooth_k=3):
    df = df.copy()
    low_min = df['Low'].rolling(window=period).min()
    high_max = df['High'].rolling(window=period).max()
    k = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    k = k.rolling(window=smooth_k).mean()
    d = k.rolling(window=smooth_k).mean()
    df['K'] = k
    df['D'] = d
    return df.dropna()

def check_market_condition():
    global current_stage, active_direction
    
    print(f"\n--- กำลังตรวจสอบตลาดรอบเวลา: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    try:
        curr_price = get_live_market_price()

        ticker = "GC=F"
        df_raw = yf.download(ticker, period="30d", interval="15m", progress=False)
        
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_raw.columns = df_raw.columns.get_level_values(0)
        
        if df_raw.empty or len(df_raw) < 50:
            ticker = "XAUUSD=X"
            df_raw = yf.download(ticker, period="30d", interval="15m", progress=False)
            if isinstance(df_raw.columns, pd.MultiIndex):
                df_raw.columns = df_raw.columns.get_level_values(0)

        df_15m = df_raw.dropna()
        df_1h = df_raw.resample('1h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        df_4h = df_raw.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        
        if not df_15m.empty:
            df_15m.iloc[-1, df_15m.columns.get_loc('Close')] = curr_price
            if curr_price > df_15m.iloc[-1]['High']:
                df_15m.iloc[-1, df_15m.columns.get_loc('High')] = curr_price
            if curr_price < df_15m.iloc[-1]['Low']:
                df_15m.iloc[-1, df_15m.columns.get_loc('Low')] = curr_price

        df_4h_ind = calculate_stochastic(df_4h)
        df_1h_ind = calculate_stochastic(df_1h)
        df_15m_ind = calculate_stochastic(df_15m)
        
        curr_4h = df_4h_ind['K'].iloc[-1]
        curr_1h = df_1h_ind['K'].iloc[-1]
        
        curr_15m = df_15m_ind['K'].iloc[-1]
        prev_15m = df_15m_ind['K'].iloc[-2]
        curr_d_15m = df_15m_ind['D'].iloc[-1]
        prev_d_15m = df_15m_ind['D'].iloc[-2]
        
        print(f"ราคา: {curr_price:.2f} | Stage: {current_stage} | Direction: {active_direction}")
        print(f"Stoch -> 4H: {curr_4h:.2f} | 1H: {curr_1h:.2f} | 15M K: {curr_15m:.2f}")

        # --- STAGE 1 ---
        if current_stage == 1:
            if curr_4h > 55:
                current_stage = 2
                active_direction = "HIGH"
                msg = (
                    "🚨 *ZONE TRIGGER // XAUUSD (Auto 24H)*\n"
                    "🛡️ *[Stage 1]* 4H UP TO HIGH ZONE\n"
                    f"💰 ราคาตลาด: {curr_price:.2f} | 4H K = {curr_4h:.2f}\n"
                    "👉 รอสัญญาณโซน HIGH ด่าน 2 (1H K > 85)"
                )
                send_telegram(msg)
                print(">>> ผ่านด่าน 1 ฝั่ง HIGH ส่งแจ้งเตือนแล้ว")
            elif curr_4h < 45:
                current_stage = 2
                active_direction = "LOW"
                msg = (
                    "🚨 *ZONE TRIGGER // XAUUSD (Auto 24H)*\n"
                    "📉 *[Stage 1]* 4H DOWN TO LOW ZONE\n"
                    f"💰 ราคาตลาด: {curr_price:.2f} | 4H K = {curr_4h:.2f}\n"
                    "👉 รอสัญญาณโซน LOW ด่าน 2 (1H K < 15)"
                )
                send_telegram(msg)
                print(">>> ผ่านด่าน 1 ฝั่ง LOW ส่งแจ้งเตือนแล้ว")
        
        # --- STAGE 2 ---
        elif current_stage == 2:
            if active_direction == "HIGH":
                if curr_1h > 85:
                    current_stage = 3
                    msg = (
                        "🚨 *ZONE TRIGGER // XAUUSD (Auto 24H)*\n"
                        "⚡ *[Stage 2]* 1H HIGH ZONE\n"
                        f"💰 ราคาตลาด: {curr_price:.2f} | 1H K = {curr_1h:.2f}\n"
                        "👉 รอสัญญาณ 15M Cross Above 80 (ด่าน 3)"
                    )
                    send_telegram(msg)
                    print(">>> ผ่านด่าน 2 ฝั่ง HIGH ส่งแจ้งเตือนแล้ว")
            elif active_direction == "LOW":
                if curr_1h < 15:
                    current_stage = 3
                    msg = (
                        "🚨 *ZONE TRIGGER // XAUUSD (Auto 24H)*\n"
                        "⚡ *[Stage 2]* 1H LOW ZONE\n"
                        f"💰 ราคาตลาด: {curr_price:.2f} | 1H K = {curr_1h:.2f}\n"
                        "👉 รอสัญญาณ 15M Cross Under 20 (ด่าน 3)"
                    )
                    send_telegram(msg)
                    print(">>> ผ่านด่าน 2 ฝั่ง LOW ส่งแจ้งเตือนแล้ว")
        
        # --- STAGE 3 ---
        elif current_stage == 3:
            if active_direction == "HIGH":
                is_cross_above_80 = (curr_15m >= 80) and (prev_15m <= prev_d_15m) and (curr_15m > curr_d_15m)
                if is_cross_above_80:
                    msg = (
                        "🔥 *🚨 ZONE TRIGGER // XAUUSD (Auto 24H)*\n"
                        "🛑 *[Stage 3]* 15M HIGH ZONE TRIGGER\n"
                        f"💰 ราคาตลาด: {curr_price:.2f} | 15M K = {curr_15m:.2f}\n"
                        "🏁 *ปิดรอบสมบูรณ์! เริ่มรอบใหม่รอ Stage 1*"
                    )
                    send_telegram(msg)
                    print(">>> ครบ 3 ด่านฝั่ง HIGH แจ้งเตือนและรีเซ็ตรอบใหม่แล้ว")
                    current_stage = 1
                    active_direction = None
            elif active_direction == "LOW":
                is_cross_under_20 = (curr_15m <= 20) and (prev_15m >= prev_d_15m) and (curr_15m < curr_d_15m)
                if is_cross_under_20:
                    msg = (
                        "🔥 *🚨 ZONE TRIGGER // XAUUSD (Auto 24H)*\n"
                        "🛑 *[Stage 3]* 15M LOW ZONE TRIGGER\n"
                        f"💰 ราคาตลาด: {curr_price:.2f} | 15M K = {curr_15m:.2f}\n"
                        "🏁 *ปิดรอบสมบูรณ์! เริ่มรอบใหม่รอ Stage 1*"
                    )
                    send_telegram(msg)
                    print(">>> ครบ 3 ด่านฝั่ง LOW แจ้งเตือนและรีเซ็ตรอบใหม่แล้ว")
                    current_stage = 1
                    active_direction = None

    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการรันลูป: {e}")

if __name__ == "__main__":
    print("🤖 บอต ZONE TRIGGER XAUUSD เริ่มทำงานแบบอัตโนมัติ 24 ชม. แล้ว...")
    send_telegram("⚡ *Bot Started:* ระบบเรดาร์ 3 ด่าน XAUUSD เริ่มทำงานสแกนอัตโนมัติ 24 ชม. แล้วครับ")
    
    while True:
        check_market_condition()
        # หน่วงเวลาก่อนเช็กรอบถัดไป (เช่น ทุกๆ 5 นาที)
        time.sleep(CHECK_INTERVAL_SECONDS)
