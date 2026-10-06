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

# ใช้ st.session_state เพื่อเก็บสถานะและค่า Stoch RSI ล่าสุดของแต่ละ TF
if "bot_status" not in st.session_state:
    st.session_state.bot_status = "Stopped"
if "current_stage" not in st.session_state:
    st.session_state.current_stage = 1
if "target_direction" not in st.session_state:
    st.session_state.target_direction = "-"
if "logs" not in st.session_state:
    st.session_state.logs = []

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
    
    if "📢" in message or "🔥" in message or "🚀" in message or "🛑" in message:
        send_telegram_notification(log_entry, tg_token, tg_chat_id)

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

def update_all_stoch_rsi():
    """ ฟังก์ชันช่วยดึงและคำนวณค่า Stoch RSI ของทุก Timeframe เพื่ออัปเดตหน้าจอ """
    try:
        # 4H
        df_4h = fetch_data(period="60d", interval="4h")
        if df_4h is not None and not df_4h.empty:
            k_4h, d_4h = calculate_stochastic_rsi(df_4h)
            st.session_state.stoch_rsi_4h = {"k": float(k_4h.iloc[-1]), "d": float(d_4h.iloc[-1])}
        
        # 1H
        df_1h = fetch_data(period="14d", interval="1h")
        if df_1h is not None and not df_1h.empty:
            k_1h, d_1h = calculate_stochastic_rsi(df_1h)
            st.session_state.stoch_rsi_1h = {"k": float(k_1h.iloc[-1]), "d": float(d_1h.iloc[-1])}
            
        # 15M
        df_15m = fetch_data(period="5d", interval="15m")
        if df_15m is not None and not df_15m.empty:
            k_15m, d_15m = calculate_stochastic_rsi(df_15m)
            st.session_state.stoch_rsi_15m = {"k": float(k_15m.iloc[-1]), "d": float(d_15m.iloc[-1])}
    except Exception as e:
        pass

# ==========================================
# BACKGROUND BOT WORKER
# ==========================================
def run_bot(tg_token, tg_chat_id):
    while st.session_state.bot_status == "Running":
        try:
            update_all_stoch_rsi() # อัปเดตค่าทุกรอบการทำงาน
            
            stage = st.session_state.current_stage
            direction = st.session_state.target_direction
            
            if stage == 1:
                k_4h_val = st.session_state.stoch_rsi_4h["k"]
                if k_4h_val > 55:
                    msg = f"📢 *[Stage 1]*: 4H Stoch RSI TO HIGH ZONE\nK = {k_4h_val:.2f}\n👉 รอสัญญาณ HIGH ZONE STAGE 2"
                    add_log(msg, tg_token, tg_chat_id)
                    st.session_state.target_direction = "HIGH"
                    st.session_state.current_stage = 2
                elif k_4h_val < 45:
                    msg = f"📢 *[Stage 1]*: 4H Stoch RSI TO LOW ZONE\nK = {k_4h_val:.2f}\n👉 รอสัญญาณ LOW ZONE STAGE 2"
                    add_log(msg, tg_token, tg_chat_id)
                    st.session_state.target_direction = "LOW"
                    st.session_state.current_stage = 2
                        
            elif stage == 2:
                k_1h_val = st.session_state.stoch_rsi_1h["k"]
                if direction == "HIGH" and k_1h_val > 80:
                    msg = f"📢 *[Stage 2]*: 1H Stoch RSI HIGH ZONE\nK = {k_1h_val:.2f}\n👉 รอสัญญาณ HIGH ZONE STAGE 3"
                    add_log(msg, tg_token, tg_chat_id)
                    st.session_state.current_stage = 3
                elif direction == "LOW" and k_1h_val < 20:
                    msg = f"📢 *[Stage 2]*: 1H Stoch RSI LOW ZONE\nK = {k_1h_val:.2f}\n👉 รอสัญญาณ LOW ZONE STAGE 3"
                    add_log(msg, tg_token, tg_chat_id)
                    st.session_state.current_stage = 3
                        
            elif stage == 3:
                df_15m = fetch_data(period="5d", interval="15m")
                if df_15m is not None and not df_15m.empty:
                    k_15m, d_15m = calculate_stochastic_rsi(df_15m)
                    latest_k = float(k_15m.iloc[-1])
                    latest_d = float(d_15m.iloc[-1])
                    prev_k = float(k_15m.iloc[-2])
                    prev_d = float(d_15m.iloc[-2])
                    
                    is_bullish_cross = (prev_k < prev_d) and (latest_k > latest_d)
                    is_bearish_cross = (prev_k > prev_d) and (latest_k < latest_d)
                    
                    if direction == "HIGH" and latest_k > 80 and is_bearish_cross:
                        msg = f"🔥 *[Stage 3]*: 15M HIGH ZONE TRIGGER (Bearish Cross)\nK = {latest_k:.2f}\n✅ ปิดรอบครบ 3 Stage! เริ่มรอบใหม่ Stage 1"
                        add_log(msg, tg_token, tg_chat_id)
                        st.session_state.current_stage = 1
                        st.session_state.target_direction = "-"
                    elif direction == "LOW" and latest_k < 20 and is_bullish_cross:
                        msg = f"🔥 *[Stage 3]*: 15M LOW ZONE TRIGGER (Bullish Cross)\nK = {latest_k:.2f}\n✅ ปิดรอบครบ 3 Stage! เริ่มรอบใหม่ Stage 1"
                        add_log(msg, tg_token, tg_chat_id)
                        st.session_state.current_stage = 1
                        st.session_state.target_direction = "-"
                        
        except Exception as e:
            add_log(f"⚠️ Error in loop: {str(e)}", tg_token, tg_chat_id)
            
        for _ in range(60):
            if st.session_state.bot_status != "Running":
                break
            time.sleep(1)

# ==========================================
# STREAMLIT UI
# ==========================================
st.title("🛡️ XAUUSD Zone Trigger Bot Dashboard")
st.markdown("ระบบเฝ้าระกราฟทองคำอัตโนมัติ 3 Stages พร้อม Stoch RSI และระบบแจ้งเตือน Telegram แบบ Real-Time")

st.sidebar.header("⚙️ Telegram Settings")
telegram_token = st.sidebar.text_input("Bot Token", type="password", placeholder="ใส่ Bot Token")
telegram_chat_id = st.sidebar.text_input("Chat ID", placeholder="ใส่ Chat ID")

st.sidebar.markdown("---")
st.sidebar.subheader("🧪 ทดสอบการเชื่อมต่อ")
if st.sidebar.button("📤 ส่งข้อความทดสอบไป Telegram"):
    if telegram_token and telegram_chat_id:
        success = send_telegram_notification("🟢 *ทดสอบการเชื่อมต่อสำเร็จ!* บอท XAUUSD พร้อมส่งแจ้งเตือนแล้วค่ะ", telegram_token, telegram_chat_id)
        if success:
            st.sidebar.success("✅ ส่งข้อความสำเร็จ! เช็คใน Telegram ได้เลย")
        else:
            st.sidebar.error("❌ ส่งไม่ผ่าน กรุณาตรวจสอบ Token และ Chat ID อีกครั้ง")
    else:
        st.sidebar.warning("⚠️ กรุณากรอก Bot Token และ Chat ID ก่อนกดทดสอบ")

# โหลดค่า Stoch RSI มารอไว้ทันทีตั้งแต่เปิดหน้าเว็บครั้งแรก
if st.session_state.stoch_rsi_4h["k"] == 0.0:
    update_all_stoch_rsi()

status_placeholder = st.empty()

def render_dashboard_metrics():
    with status_placeholder.container():
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Bot Status", st.session_state.bot_status)
        with col2:
            st.metric("Current Stage", f"Stage {st.session_state.current_stage}")
        with col3:
            st.metric("Target Direction", st.session_state.target_direction)

render_dashboard_metrics()

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
        if st.session_state.bot_status != "Running":
            st.session_state.bot_status = "Running"
            st.session_state.current_stage = 1
            st.session_state.target_direction = "-"
            
            update_all_stoch_rsi() # ดึงค่าล่าสุดมาก่อนเริ่มรัน
            add_log("🚀 XAUUSD Zone Trigger Bot Started...", telegram_token, telegram_chat_id)
            
            t = threading.Thread(target=run_bot, args=(telegram_token, telegram_chat_id), daemon=True)
            t.start()
            
            st.rerun()
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

if st.session_state.bot_status == "Running":
    time.sleep(5)
    st.rerun()
