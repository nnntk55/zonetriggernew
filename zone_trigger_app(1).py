import time
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
import threading
import requests

# ==========================================
# CONFIGURATION & PAGE SETUP
# ==========================================
st.set_page_config(
    page_title="XAUUSD Zone Trigger Bot",
    page_icon="📈",
    layout="wide"
)

SYMBOL = "GC=F"  # ใช้ Yahoo Finance Symbol สำหรับทองคำ

# กำหนดค่าเริ่มต้นให้กับ session_state และระบบจำค่า Telegram
if "bot_status" not in st.session_state:
    st.session_state.bot_status = "Stopped"
if "current_stage" not in st.session_state:
    st.session_state.current_stage = 1
if "target_direction" not in st.session_state:
    st.session_state.target_direction = "-"
if "logs" not in st.session_state:
    st.session_state.logs = []

# ตัวแปรจำค่า Telegram
if "saved_telegram_token" not in st.session_state:
    st.session_state.saved_telegram_token = ""
if "saved_telegram_chat_id" not in st.session_state:
    st.session_state.saved_telegram_chat_id = ""

if "stoch_rsi_4h" not in st.session_state:
    st.session_state.stoch_rsi_4h = {"k": 0.0, "d": 0.0}
if "stoch_rsi_1h" not in st.session_state:
    st.session_state.stoch_rsi_1h = {"k": 0.0, "d": 0.0}
if "stoch_rsi_15m" not in st.session_state:
    st.session_state.stoch_rsi_15m = {"k": 0.0, "d": 0.0}

def send_telegram_notification(message, token, chat_id):
    """ ฟังก์ชันส่งข้อความเข้า Telegram """
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            res = requests.post(url, json=payload, timeout=10)
            return res.status_code == 200
        except Exception as e:
            print(f"Telegram error: {e}")
            return False
    return False

def add_log(message, tg_token="", tg_chat_id=""):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    st.session_state.logs.insert(0, log_entry)
    if len(st.session_state.logs) > 50:
        st.session_state.logs.pop()
    
    # หากเป็นข้อความแจ้งเตือน (มีอีโมจิพิเศษ) จะส่งเข้า Telegram โดยไม่แนบวัน-เวลา
    if any(emoji in message for emoji in ["📢", "🔥", "🚀", "🛑"]):
        send_telegram_notification(message, tg_token, tg_chat_id)

def calculate_stochastic_rsi(df, rsi_period=14, stoch_period=14, k_period=3, d_period=3):
    """ คำนวณค่า Stochastic RSI (%K และ %D) """
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    lowest_rsi = rsi.rolling(window=stoch_period).min()
    highest_rsi = rsi.rolling(window=stoch_period).max()
    
    stoch_rsi = (rsi - lowest_rsi) / (highest_rsi - lowest_rsi) * 100
    k = stoch_rsi.rolling(window=k_period).mean()
    d = k.rolling(window=d_period).mean()
    return k, d

def fetch_data(period, interval):
    try:
        data = yf.download(SYMBOL, period=period, interval=interval, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
        return data
    except Exception as e:
        return None

def update_all_stoch_rsi(tg_token, tg_chat_id):
    """ ดึงข้อมูลและคำนวณค่า Stoch RSI พร้อมแจ้งเตือนทุกย่างก้าวของ Stage """
    try:
        # 1. เช็ก Stage 1 (ดู Timeframe 4H)
        if st.session_state.current_stage == 1:
            df_4h = fetch_data(period="60d", interval="4h")
            if df_4h is not None and not df_4h.empty:
                k_4h, d_4h = calculate_stochastic_rsi(df_4h)
                k_val = float(k_4h.iloc[-1])
                d_val = float(d_4h.iloc[-1])
                st.session_state.stoch_rsi_4h = {"k": k_val, "d": d_val}
                
                if k_val > 55:
                    st.session_state.target_direction = "HIGH"
                    st.session_state.current_stage = 2
                    msg = f"📢 *[Stage 1 ผ่านแล้ว]*: 4H Stoch RSI (%K = {k_val:.2f}) เข้าโซน HIGH 📈\n👉 ย้ายเข้าสู่ *Stage 2* (รอ 1H คอนเฟิร์มโซน)"
                    add_log(msg, tg_token, tg_chat_id)
                elif k_val < 45:
                    st.session_state.target_direction = "LOW"
                    st.session_state.current_stage = 2
                    msg = f"📢 *[Stage 1 ผ่านแล้ว]*: 4H Stoch RSI (%K = {k_val:.2f}) เข้าโซน LOW 📉\n👉 ย้ายเข้าสู่ *Stage 2* (รอ 1H คอนเฟิร์มโซน)"
                    add_log(msg, tg_token, tg_chat_id)

        # 2. เช็ก Stage 2 (ดู Timeframe 1H)
        if st.session_state.current_stage == 2:
            df_1h = fetch_data(period="14d", interval="1h")
            if df_1h is not None and not df_1h.empty:
                k_1h, d_1h = calculate_stochastic_rsi(df_1h)
                k_val = float(k_1h.iloc[-1])
                d_val = float(d_1h.iloc[-1])
                st.session_state.stoch_rsi_1h = {"k": k_val, "d": d_val}
                
                direction = st.session_state.target_direction
                if direction == "HIGH" and k_val > 80:
                    st.session_state.current_stage = 3
                    msg = f"📢 *[Stage 2 ผ่านแล้ว]*: 1H Stoch RSI (%K = {k_val:.2f}) ขึ้นแตะ High Zone สำเร็จ 🚀\n👉 ย้ายเข้าสู่ *Stage 3* (รอสัญญาณตัดกันใน 15M)"
                    add_log(msg, tg_token, tg_chat_id)
                elif direction == "LOW" and k_val < 20:
                    st.session_state.current_stage = 3
                    msg = f"📢 *[Stage 2 ผ่านแล้ว]*: 1H Stoch RSI (%K = {k_val:.2f}) ลงแตะ Low Zone สำเร็จ 📉\n👉 ย้ายเข้าสู่ *Stage 3* (รอสัญญาณตัดกันใน 15M)"
                    add_log(msg, tg_token, tg_chat_id)

        # 3. เช็ก Stage 3 (ดู Timeframe 15M และหาจุดตัด)
        if st.session_state.current_stage == 3:
            df_15m = fetch_data(period="5d", interval="15m")
            if df_15m is not None and not df_15m.empty:
                k_15m, d_15m = calculate_stochastic_rsi(df_15m)
                latest_k = float(k_15m.iloc[-1])
                latest_d = float(d_15m.iloc[-1])
                prev_k = float(k_15m.iloc[-2])
                prev_d = float(d_15m.iloc[-2])
                
                st.session_state.stoch_rsi_15m = {"k": latest_k, "d": latest_d}
                
                direction = st.session_state.target_direction
                is_bullish_cross = (prev_k < prev_d) and (latest_k > latest_d)
                is_bearish_cross = (prev_k > prev_d) and (latest_k < latest_d)
                
                if direction == "HIGH" and latest_k > 80 and is_bearish_cross:
                    msg = f"🔥 *[Stage 3 สำเร็จ]*: 15M HIGH ZONE TRIGGER (Bearish Cross)\nK = {latest_k:.2f} ตัด D ลงมาแล้ว! 🛑\n✅ สัญญาณครบสมบูรณ์ รีเซ็ตระบบกลับ Stage 1 เพื่อเริ่มรอบใหม่"
                    add_log(msg, tg_token, tg_chat_id)
                    st.session_state.current_stage = 1
                    st.session_state.target_direction = "-"
                elif direction == "LOW" and latest_k < 20 and is_bullish_cross:
                    msg = f"🔥 *[Stage 3 สำเร็จ]*: 15M LOW ZONE TRIGGER (Bullish Cross)\nK = {latest_k:.2f} ตัด D ขึ้นไปแล้ว! 🚀\n✅ สัญญาณครบสมบูรณ์ รีเซ็ตระบบกลับ Stage 1 เพื่อเริ่มรอบใหม่"
                    add_log(msg, tg_token, tg_chat_id)
                    st.session_state.current_stage = 1
                    st.session_state.target_direction = "-"

        # เติมข้อมูล Timeframe ที่เหลือเผื่อไว้แสดงผลหน้าจอ
        if st.session_state.current_stage != 1 and (st.session_state.stoch_rsi_4h["k"] == 0.0):
            df_4h = fetch_data(period="60d", interval="4h")
            if df_4h is not None and not df_4h.empty:
                k_4h, d_4h = calculate_stochastic_rsi(df_4h)
                st.session_state.stoch_rsi_4h = {"k": float(k_4h.iloc[-1]), "d": float(d_4h.iloc[-1])}

        if st.session_state.current_stage == 3 and (st.session_state.stoch_rsi_1h["k"] == 0.0):
            df_1h = fetch_data(period="14d", interval="1h")
            if df_1h is not None and not df_1h.empty:
                k_1h, d_1h = calculate_stochastic_rsi(df_1h)
                st.session_state.stoch_rsi_1h = {"k": float(k_1h.iloc[-1]), "d": float(d_1h.iloc[-1])}

    except Exception as e:
        pass

# ==========================================
# BACKGROUND BOT WORKER
# ==========================================
def run_bot(tg_token, tg_chat_id):
    while st.session_state.bot_status == "Running":
        try:
            update_all_stoch_rsi(tg_token, tg_chat_id)
        except Exception as e:
            add_log(f"⚠️ Error in loop: {str(e)}", tg_token, tg_chat_id)
            
        for _ in range(15):  # เช็กทุกๆ 15 วินาที
            if st.session_state.bot_status != "Running":
                break
            time.sleep(1)

# ==========================================
# STREAMLIT UI
# ==========================================
st.title("🛡️ XAUUSD Zone Trigger Bot Dashboard")
st.markdown("ระบบเฝ้าระกราฟทองคำอัตโนมัติ 3 Stages พร้อม Stoch RSI, ระบบจำค่า Telegram และส่งแจ้งเตือน (แบบไม่มีวันเวลา) อัตโนมัติ")

st.sidebar.header("⚙️ Telegram Settings (Session Saved)")

# ฟอร์มรับค่า Telegram พร้อมระบบจำค่าอัตโนมัติ
with st.sidebar.form("telegram_config_form"):
    input_token = st.text_input("Bot Token", value=st.session_state.saved_telegram_token, type="password", placeholder="ใส่ Bot Token")
    input_chat_id = st.text_input("Chat ID", value=st.session_state.saved_telegram_chat_id, placeholder="ใส่ Chat ID")
    
    save_button = st.form_submit_button("💾 บันทึกค่า Telegram", use_container_width=True)
    if save_button:
        st.session_state.saved_telegram_token = input_token
        st.session_state.saved_telegram_chat_id = input_chat_id
        st.sidebar.success("✅ บันทึกค่า Telegram เรียบร้อยแล้ว!")

# ดึงค่าที่จำไว้มาใช้งานต่อ
telegram_token = st.session_state.saved_telegram_token
telegram_chat_id = st.session_state.saved_telegram_chat_id

st.sidebar.markdown("---")
st.sidebar.subheader("🧪 ทดสอบการเชื่อมต่อ")
if st.sidebar.button("📤 ส่งข้อความทดสอบไป Telegram", use_container_width=True):
    if telegram_token and telegram_chat_id:
        success = send_telegram_notification("🟢 *ทดสอบการเชื่อมต่อสำเร็จ!* บอทพร้อมส่งแจ้งเตือนทุก Stage แบบไม่มีวันเวลาแล้วค่ะ", telegram_token, telegram_chat_id)
        if success:
            st.sidebar.success("✅ ส่งข้อความสำเร็จ!")
        else:
            st.sidebar.error("❌ ส่งไม่ผ่าน กรุณาตรวจสอบ Token และ Chat ID")
    else:
        st.sidebar.warning("⚠️ กรุณากรอกและบันทึก Bot Token / Chat ID ก่อน")

# อัปเดตข้อมูลทันทีเมื่อเปิดหน้าเว็บ
update_all_stoch_rsi(telegram_token, telegram_chat_id)

# แสดงผล Dashboard Metrics ด้านบน
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Bot Status", st.session_state.bot_status)
with col2:
    st.metric("Current Stage", f"Stage {st.session_state.current_stage}")
with col3:
    st.metric("Target Direction", st.session_state.target_direction)

# แสดงผลค่า Stochastic RSI ในแต่ละ Timeframe
st.markdown("---")
st.subheader("📊 Stochastic RSI Status by Timeframe")
tf_col1, tf_col2, tf_col3 = st.columns(3)

with tf_col1:
    s4h = st.session_state.stoch_rsi_4h
    st.metric("4H Stoch RSI (%K)", f"{s4h['k']:.2f}", f"D: {s4h['d']:.2f}")

with tf_col2:
    s1h = st.session_state.stoch_rsi_1h
    st.metric("1H Stoch RSI (%K)", f"{s1h['k']:.2f}", f"D: {s1h['d']:.2f}")

with tf_col3:
    s15m = st.session_state.stoch_rsi_15m
    st.metric("15M Stoch RSI (%K)", f"{s15m['k']:.2f}", f"D: {s15m['d']:.2f}")

st.divider()

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if st.button("▶️ Start Bot", use_container_width=True):
        if telegram_token and telegram_chat_id:
            if st.session_state.bot_status != "Running":
                st.session_state.bot_status = "Running"
                update_all_stoch_rsi(telegram_token, telegram_chat_id)
                add_log("🚀 XAUUSD Zone Trigger Bot Started (Clean Alert All Stages)...", telegram_token, telegram_chat_id)
                
                t = threading.Thread(target=run_bot, args=(telegram_token, telegram_chat_id), daemon=True)
                t.start()
                st.rerun()
        else:
            st.warning("⚠️ กรุณากรอกและบันทึก Bot Token และ Chat ID ในเมนูด้านซ้ายก่อนกด Start Bot ครับ")
with col_btn2:
    if st.button("⏹️ Stop Bot", use_container_width=True):
        if st.session_state.bot_status == "Running":
            st.session_state.bot_status = "Stopped"
            add_log("🛑 Bot Stopped by user.", telegram_token, telegram_chat_id)
            st.rerun()

st.subheader("📋 Real-Time Activity Logs")
log_container = st.container(height=400)
with log_container:
    for log in st.session_state.logs:
        st.text(log)

# รีเฟรชหน้าจออัตโนมัติทุกๆ 10 วินาที
if st.session_state.bot_status == "Running":
    time.sleep(10)
    st.rerun()
