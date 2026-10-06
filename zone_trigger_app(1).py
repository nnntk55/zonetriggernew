import streamlit as st
import time
import requests
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="ZONE TRIGGER // XAUUSD Live Pro", page_icon="⚡", layout="centered")

st.title("⚡ ZONE TRIGGER // XAUUSD Live Radar")
st.markdown("ระบบสแกนและควบคุมลำดับสัญญาณ 3 ด่าน (4H ➔ 1H ➔ 15M) อิงราคาตลาดจริง XAUUSD สดๆ พร้อมระบบล็อกสถานะและแจ้งเตือน Telegram อัตโนมัติ")

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
    st.session_state["active_direction"] = None  # "SELL" or "BUY"

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

if st.sidebar.button("🧪 ทดสอบส่งข้อความเข้า Telegram"):
    success, msg = send_telegram(bot_token, chat_id, "⚡ *Test Alert* จากระบบ ZONE TRIGGER XAUUSD พร้อมทำงานแล้ว!")
    if success:
        st.sidebar.success(msg)
    else:
        st.sidebar.error(msg)

st.markdown("---")
st.subheader("🎯 สถานะเรดาร์ปัจจุบัน (State Machine)")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("ด่านปัจจุบัน", f"Stage {st.session_state['current_stage']}")
with col2:
    st.metric("ทิศทางเป้าหมาย", str(st.session_state['active_direction']) if st.session_state['active_direction'] else "รอสัญญาณด่าน 1")
with col3:
    st.metric("สินทรัพย์อ้างอิง", "XAUUSD (Spot Gold)", "Live Data")

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
        st.error("⚠️ กรุณากรอก Telegram Bot Token และ Chat ID ที่ Sidebar ด้านซ้ายก่อนกดสแกน")
    else:
        with st.spinner("กำลังดึงข้อมูลราคาทองคำ XAUUSD ล่าสุดจากตลาด..."):
            try:
                ticker = "XAUUSD=X"
                
                df_raw = yf.download(ticker, period="30d", interval="15m", progress=False)
                if isinstance(df_raw.columns, pd.MultiIndex):
                    df_raw.columns = df_raw.columns.get_level_values(0)
                
                if df_raw.empty:
                    ticker = "GC=F"
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
                
                df_4h_ind = calculate_stochastic(df_4h)
                df_1h_ind = calculate_stochastic(df_1h)
                df_15m_ind = calculate_stochastic(df_15m)
                
                curr_price = df_15m['Close'].iloc[-1]
                curr_4h = df_4h_ind['K'].iloc[-1]
                curr_1h = df_1h_ind['K'].iloc[-1]
                
                curr_15m = df_15m_ind['K'].iloc[-1]
                prev_15m = df_15m_ind['K'].iloc[-2]
                curr_d_15m = df_15m_ind['D'].iloc[-1]
                prev_d_15m = df_15m_ind['D'].iloc[-2]
                
                st.success(f"✅ ดึงข้อมูลสำเร็จ! ราคาปัจจุบัน: **{curr_price:.2f} USD**")
                st.write(f"📊 **ค่า Stochastic:** 4H K = **{curr_4h:.2f}** | 1H K = **{curr_1h:.2f}** | 15M K = **{curr_15m:.2f}**")
                
                stage = st.session_state["current_stage"]
                direction = st.session_state["active_direction"]
                
                # --- STAGE 1 ---
                if stage == 1:
                    if curr_4h > 55:
                        st.session_state["current_stage"] = 2
                        st.session_state["active_direction"] = "SELL"
                        msg = (
                            "🚨 *ZONE TRIGGER // XAUUSD*\n"
                            "🛡️ *[Stage 1]* 4H UP TO HIGH ZONE\n"
                            f"💰 ราคา: {curr_price:.2f} | 4H K = {curr_4h:.2f}\n"
                            "👉 รอสัญญาณโซน HIGH (1H K > 85)"
                        )
                        send_telegram(bot_token, chat_id, msg)
                        st.info("🎯 ผ่านด่าน 1 ฝั่ง SELL สำเร็จ! ระบบเลื่อนไปรอสัญญาณ 1H โซน SELL")
                    elif curr_4h < 45:
                        st.session_state["current_stage"] = 2
                        st.session_state["active_direction"] = "BUY"
                        msg = (
                            "🚨 *ZONE TRIGGER // XAUUSD*\n"
                            "📉 *[Stage 1]* 4H DOWN TO LOW ZONE\n"
                            f"💰 ราคา: {curr_price:.2f} | 4H K = {curr_4h:.2f}\n"
                            "👉 รอสัญญาณโซน LOW (1H K < 15)"
                        )
                        send_telegram(bot_token, chat_id, msg)
                        st.info("🎯 ผ่านด่าน 1 ฝั่ง BUY สำเร็จ! ระบบเลื่อนไปรอสัญญาณ 1H โซน BUY")
                    else:
                        st.warning(f"⏳ ด่าน 1: 4H K อยู่ที่ {curr_4h:.2f} (ยังไม่ทะลุ > 55 หรือ < 45)")
                
                # --- STAGE 2 ---
                elif stage == 2:
                    if direction == "SELL":
                        if curr_1h > 85:
                            st.session_state["current_stage"] = 3
                            msg = (
                                "🚨 *ZONE TRIGGER // XAUUSD*\n"
                                "⚡ *[Stage 2]* 1H HIGH ZONE\n"
                                f"💰 ราคา: {curr_price:.2f} | 1H K = {curr_1h:.2f}\n"
                                "👉 รอสัญญาณ 15M STOCH CROSSED > 80"
                            )
                            send_telegram(bot_token, chat_id, msg)
                            st.info("🎯 ผ่านด่าน 2 ฝั่ง SELL สำเร็จ! ระบบเลื่อนไปรอสัญญาณด่าน 3 (15M)")
                        else:
                            st.warning(f"⏳ กำลังเฝ้าระวังด่าน 2 (SELL): 1H K = {curr_1h:.2f} (ต้องมากกว่า 85)")
                    elif direction == "BUY":
                        if curr_1h < 15:
                            st.session_state["current_stage"] = 3
                            msg = (
                                "🚨 *ZONE TRIGGER // XAUUSD*\n"
                                "⚡ *[Stage 2]* 1H LOW ZONE\n"
                                f"💰 ราคา: {curr_price:.2f} | 1H K = {curr_1h:.2f}\n"
                                "👉 รอสัญญาณ 15M STOCH CROSSED < 20"
                            )
                            send_telegram(bot_token, chat_id, msg)
                            st.info("🎯 ผ่านด่าน 2 ฝั่ง BUY สำเร็จ! ระบบเลื่อนไปรอสัญญาณด่าน 3 (15M)")
                        else:
                            st.warning(f"⏳ กำลังเฝ้าระวังด่าน 2 (BUY): 1H K = {curr_1h:.2f} (ต้องน้อยกว่า 15)")
                
                # --- STAGE 3 ---
                elif stage == 3:
                    if direction == "SELL":
                        is_cross_above_80 = (curr_15m >= 80) and (prev_15m <= prev_d_15m) and (curr_15m > curr_d_15m)
                        if is_cross_above_80:
                            msg = (
                                "🔥 *🚨 ZONE TRIGGER // XAUUSD*\n"
                                "🛑 *[Stage 3]* 15M HIGH ZONE TRIGGER\n"
                                f"💰 ราคาปิด: {curr_price:.2f} | 15M K = {curr_15m:.2f}\n"
                                "🏁 *ปิดรอบสมบูรณ์! เริ่มรอบใหม่รอ Stage 1*"
                            )
                            send_telegram(bot_token, chat_id, msg)
                            st.success("🎯 ครบ 3 ด่านฝั่ง SELL สมบูรณ์! รีเซ็ตรอบกลับไปเริ่มต้นด่าน 1 ใหม่")
                            st.session_state["current_stage"] = 1
                            st.session_state["active_direction"] = None
                        else:
                            st.warning(f"⏳ กำลังเฝ้าระวังด่าน 3 (SELL): รอ 15M Cross Above 80 (ปัจจุบัน K = {curr_15m:.2f})")
                    elif direction == "BUY":
                        is_cross_under_20 = (curr_15m <= 20) and (prev_15m >= prev_d_15m) and (curr_15m < curr_d_15m)
                        if is_cross_under_20:
                            msg = (
                                "🔥 *🚨 ZONE TRIGGER // XAUUSD*\n"
                                "🛑 *[Stage 3]* 15M LOW ZONE TRIGGER\n"
                                f"💰 ราคาปิด: {curr_price:.2f} | 15M K = {curr_15m:.2f}\n"
                                "🏁 *ปิดรอบสมบูรณ์! เริ่มรอบใหม่รอ Stage 1*"
                            )
                            send_telegram(bot_token, chat_id, msg)
                            st.success("🎯 ครบ 3 ด่านฝั่ง BUY สมบูรณ์! รีเซ็ตรอบกลับไปเริ่มต้นด่าน 1 ใหม่")
                            st.session_state["current_stage"] = 1
                            st.session_state["active_direction"] = None
                        else:
                            st.warning(f"⏳ กำลังเฝ้าระวังด่าน 3 (BUY): รอ 15M Cross Under 20 (ปัจจุบัน K = {curr_15m:.2f})")
                            
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")

st.markdown("---")
st.markdown("💡 **เงื่อนไขการทำงานของระบบ:** แอปนี้จะดึงข้อมูลราคา Spot ทองคำ (XAUUSD) ที่มีความใกล้เคียงกับ Exness และ TradingView มากที่สุดมาคำนวณ Stochastic ตามเงื่อนไข 3 ด่านแบบเป๊ะๆ เมื่อครบกระบวนการจะรีเซ็ตกลับมารอด่าน 1 ให้อัตโนมัติ")
