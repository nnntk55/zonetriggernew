import streamlit as st
import time
import requests
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="ZONE TRIGGER // XAUUSD Live Auto", page_icon="⚡", layout="centered")

st.title("⚡ ZONE TRIGGER // XAUUSD Live Radar (Auto Sync)")
st.markdown("ระบบสแกนและควบคุมลำดับสัญญาณ 3 ด่าน (4H ➔ 1H ➔ 15M) ดึงราคาอัตโนมัติ")

# Sidebar settings
st.sidebar.header("⚙️ ตั้งค่าระบบ Telegram")
bot_token = st.sidebar.text_input("Telegram Bot Token", type="password", placeholder="เช่น 123456789:ABCdef...")
chat_id = st.sidebar.text_input("Telegram Chat ID", placeholder="เช่น 987654321")

st.sidebar.header("🔄 ควบคุมสถานะระบบ")
if st.sidebar.button("♻️ รีเซ็ตสถานะกลับไปด่าน 1"):
    st.session_state["current_stage"] = 1
    st.session_state["active_direction"] = None
    st.success("รีเซ็ตสถานะเรียบร้อย เริ่มต้นใหม่ที่ด่าน 1")

# Initialize Session State
if "current_stage" not in st.session_state:
    st.session_state["current_stage"] = 1
if "active_direction" not in st.session_state:
    st.session_state["active_direction"] = None  # "HIGH" or "LOW"

def send_telegram(token, chat_id, message):
    if not token or not chat_id:
        return False, "กรุณากรอก Bot Token และ Chat ID ให้ครบถ้วน"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            return True, "ส่งข้อความสำเร็จ!"
        else:
            return False, f"Telegram Error: {res.text}"
    except Exception as e:
        return False, str(e)

# ฟังก์ชันดึงราคาอัตโนมัติ (เลือกตัวที่ตรงกับตลาด Spot ทองคำจริงที่สุด)
def get_live_market_price():
    tickers = ["GC=F", "XAUUSD=X"]
    for t in tickers:
        try:
            ticker = yf.Ticker(t)
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                val = float(hist['Close'].iloc[-1])
                if val > 1000:  # กรองราคาให้สมเหตุสมผล
                    return val
        except:
            continue
    return 4161.00  # Fallback สำรอง

if st.sidebar.button("🧪 ทดสอบส่งข้อความเข้า Telegram"):
    success, msg = send_telegram(bot_token, chat_id, "⚡ *Test Alert* จากระบบ ZONE TRIGGER XAUUSD พร้อมทำงานออโต้อีกครั้งแล้ว!")
    if success:
        st.sidebar.success(msg)
    else:
        st.sidebar.error(msg)

st.markdown("---")
st.subheader("🎯 สถานะเรดาร์ปัจจุบัน (State Machine)")

current_price_display = get_live_market_price()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("ด่านปัจจุบัน", f"Stage {st.session_state['current_stage']}")
with col2:
    st.metric("ทิศทางเป้าหมาย", str(st.session_state['active_direction']) if st.session_state['active_direction'] else "รอสัญญาณด่าน 1")
with col3:
    st.metric("ราคาตลาดสด (Auto)", f"{current_price_display:.2f} USD")

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

if st.button("🔍 กดสแกนกราฟและเช็กเงื่อนไขเรียลไทม์", type="primary"):
    if not bot_token or not chat_id:
        st.error("⚠ กรุณากรอก Telegram Bot Token และ Chat ID ที่ Sidebar ด้านซ้ายก่อนกดสแกน")
    else:
        with st.spinner("กำลังดึงราคาสดและประมวลผลข้อมูลแท่งเทียน..."):
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
                
                df_1h = df_raw.resample('1h').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
                }).dropna()
                
                df_4h = df_raw.resample('4h').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
                }).dropna()
                
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
                
                st.success(f"✅ สแกนสำเร็จ | ราคาอ้างอิงอัตโนมัติ: **{curr_price:.2f} USD**")
                st.write(f"📊 **ค่า Stochastic:** 4H K = **{curr_4h:.2f}** | 1H K = **{curr_1h:.2f}** | 15M K = **{curr_15m:.2f}**")
                
                stage = st.session_state["current_stage"]
                direction = st.session_state["active_direction"]
                
                # --- STAGE 1 ---
                if stage == 1:
                    if curr_4h > 55:
                        st.session_state["current_stage"] = 2
                        st.session_state["active_direction"] = "HIGH"
                        msg = (
                            "🚨 *ZONE TRIGGER // XAUUSD*\n"
                            "🛡️ *[Stage 1]* 4H UP TO HIGH ZONE\n"
                            f"💰 ราคาตลาด: {curr_price:.2f} | 4H K = {curr_4h:.2f}\n"
                            "👉 รอสัญญาณโซน HIGH ด่าน 2 (1H K > 85)"
                        )
                        send_telegram(bot_token, chat_id, msg)
                        st.info("🎯 ผ่านด่าน 1 ฝั่ง HIGH สำเร็จ!")
                    elif curr_4h < 45:
                        st.session_state["current_stage"] = 2
                        st.session_state["active_direction"] = "LOW"
                        msg = (
                            "🚨 *ZONE TRIGGER // XAUUSD*\n"
                            "📉 *[Stage 1]* 4H DOWN TO LOW ZONE\n"
                            f"💰 ราคาตลาด: {curr_price:.2f} | 4H K = {curr_4h:.2f}\n"
                            "👉 รอสัญญาณโซน LOW ด่าน 2 (1H K < 15)"
                        )
                        send_telegram(bot_token, chat_id, msg)
                        st.info("🎯 ผ่านด่าน 1 ฝั่ง LOW สำเร็จ!")
                    else:
                        st.warning(f"⏳ ด่าน 1: 4H K อยู่ที่ {curr_4h:.2f} (ยังไม่ทะลุ > 55 หรือ < 45)")
                
                # --- STAGE 2 ---
                elif stage == 2:
                    if direction == "HIGH":
                        if curr_1h > 85:
                            st.session_state["current_stage"] = 3
                            msg = (
                                "🚨 *ZONE TRIGGER // XAUUSD*\n"
                                "⚡ *[Stage 2]* 1H HIGH ZONE\n"
                                f"💰 ราคาตลาด: {curr_price:.2f} | 1H K = {curr_1h:.2f}\n"
                                "👉 รอสัญญาณ 15M Cross Above 80 (ด่าน 3)"
                            )
                            send_telegram(bot_token, chat_id, msg)
                            st.info("🎯 ผ่านด่าน 2 ฝั่ง HIGH สำเร็จ!")
                        else:
                            st.warning(f"⏳ กำลังเฝ้าระวังด่าน 2 (HIGH): 1H K = {curr_1h:.2f} (ต้องมากกว่า 85)")
                    elif direction == "LOW":
                        if curr_1h < 15:
                            st.session_state["current_stage"] = 3
                            msg = (
                                "🚨 *ZONE TRIGGER // XAUUSD*\n"
                                "⚡ *[Stage 2]* 1H LOW ZONE\n"
                                f"💰 ราคาตลาด: {curr_price:.2f} | 1H K = {curr_1h:.2f}\n"
                                "👉 รอสัญญาณ 15M Cross Under 20 (ด่าน 3)"
                            )
                            send_telegram(bot_token, chat_id, msg)
                            st.info("🎯 ผ่านด่าน 2 ฝั่ง LOW สำเร็จ!")
                        else:
                            st.warning(f"⏳ กำลังเฝ้าระวังด่าน 2 (LOW): 1H K = {curr_1h:.2f} (ต้องน้อยกว่า 15)")
                
                # --- STAGE 3 ---
                elif stage == 3:
                    if direction == "HIGH":
                        is_cross_above_80 = (curr_15m >= 80) and (prev_15m <= prev_d_15m) and (curr_15m > curr_d_15m)
                        if is_cross_above_80:
                            msg = (
                                "🔥 *🚨 ZONE TRIGGER // XAUUSD*\n"
                                "🛑 *[Stage 3]* 15M HIGH ZONE TRIGGER\n"
                                f"💰 ราคาตลาด: {curr_price:.2f} | 15M K = {curr_15m:.2f}\n"
                                "🏁 *ปิดรอบสมบูรณ์! เริ่มรอบใหม่รอ Stage 1*"
                            )
                            send_telegram(bot_token, chat_id, msg)
                            st.success("🎯 ครบ 3 ด่านฝั่ง HIGH สมบูรณ์! รีเซ็ตรอบใหม่")
                            st.session_state["current_stage"] = 1
                            st.session_state["active_direction"] = None
                        else:
                            st.warning(f"⏳ กำลังเฝ้าระวังด่าน 3 (HIGH): รอ 15M Cross Above 80 (K = {curr_15m:.2f})")
                    elif direction == "LOW":
                        is_cross_under_20 = (curr_15m <= 20) and (prev_15m >= prev_d_15m) and (curr_15m < curr_d_15m)
                        if is_cross_under_20:
                            msg = (
                                "🔥 *🚨 ZONE TRIGGER // XAUUSD*\n"
                                "🛑 *[Stage 3]* 15M LOW ZONE TRIGGER\n"
                                f"💰 ราคาตลาด: {curr_price:.2f} | 15M K = {curr_15m:.2f}\n"
                                "🏁 *ปิดรอบสมบูรณ์! เริ่มรอบใหม่รอ Stage 1*"
                            )
                            send_telegram(bot_token, chat_id, msg)
                            st.success("🎯 ครบ 3 ด่านฝั่ง LOW สมบูรณ์! รีเซ็ตรอบใหม่")
                            st.session_state["current_stage"] = 1
                            st.session_state["active_direction"] = None
                        else:
                            st.warning(f"⏳ กำลังเฝ้าระวังด่าน 3 (LOW): รอ 15M Cross Under 20 (K = {curr_15m:.2f})")
                            
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")

st.markdown("---")
st.markdown("💡 **ระบบทำงานแบบอัตโนมัติเต็มตัว:** ดึงราคาตลาดสดมาประมวลผลและเช็กเงื่อนไข 3 ด่านพร้อมส่งเข้า Telegram ทันทีเมื่อกดปุ่มสแกนครับ")
