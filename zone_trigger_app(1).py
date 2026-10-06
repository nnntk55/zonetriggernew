import time
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
import threading

# ==========================================
# CONFIGURATION & PAGE SETUP
# ==========================================
st.set_page_config(
    page_title="XAUUSD Zone Trigger Bot",
    page_icon="📈",
    layout="wide"
)

SYMBOL = "GC=F"  # ใช้ Yahoo Finance Symbol สำหรับทองคำ

# ใช้ st.session_state เพื่อเก็บสถานะของบอทให้คงอยู่ตลอดการรันเบื้องหลัง
if "bot_status" not in st.session_state:
    st.session_state.bot_status = "Stopped"
if "current_stage" not in st.session_state:
    st.session_state.current_stage = 1
if "target_direction" not in st.session_state:
    st.session_state.target_direction = "-"
if "logs" not in st.session_state:
    st.session_state.logs = []

def add_log(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    st.session_state.logs.insert(0, log_entry)
    # เก็บ Log ไว้สูงสุด 50 รายการล่าสุด
    if len(st.session_state.logs) > 50:
        st.session_state.logs.pop()

def calculate_stochastic(df, k_period=14, d_period=3, smooth_k=3):
    low_min = df['Low'].rolling(window=k_period).min()
    high_max = df['High'].rolling(window=k_period).max()
    fast_k = 100 * (df['Close'] - low_min) / (high_max - low_min)
    slow_k = fast_k.rolling(window=smooth_k).mean()
    slow_d = slow_k.rolling(window=d_period).mean()
    return slow_k, slow_d

def fetch_data(period, interval):
    try:
        data = yf.download(SYMBOL, period=period, interval=interval, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
        return data
    except Exception as e:
        return None

# ==========================================
# BACKGROUND BOT WORKER
# ==========================================
def run_bot():
    add_log("🚀 XAUUSD Zone Trigger Bot Started...")
    st.session_state.bot_status = "Running"
    
    while st.session_state.bot_status == "Running":
        try:
            stage = st.session_state.current_stage
            direction = st.session_state.target_direction
            
            if stage == 1:
                df_4h = fetch_data(period="60d", interval="4h")
                if df_4h is not None and not df_4h.empty:
                    k_4h, _ = calculate_stochastic(df_4h)
                    latest_k = float(k_4h.iloc[-1])
                    
                    if latest_k > 55:
                        add_log(f"📢 [Stage 1] 4H TO HIGH ZONE | Stochastic K = {latest_k:.2f} -> รอสัญญาณ HIGH ZONE STAGE 2")
                        st.session_state.target_direction = "HIGH"
                        st.session_state.current_stage = 2
                    elif latest_k < 45:
                        add_log(f"📢 [Stage 1] 4H TO LOW ZONE | Stochastic K = {latest_k:.2f} -> รอสัญญาณ LOW ZONE STAGE 2")
                        st.session_state.target_direction = "LOW"
                        st.session_state.current_stage = 2
                        
            elif stage == 2:
                df_1h = fetch_data(period="14d", interval="1h")
                if df_1h is not None and not df_1h.empty:
                    k_1h, _ = calculate_stochastic(df_1h)
                    latest_k = float(k_1h.iloc[-1])
                    
                    if direction == "HIGH" and latest_k > 85:
                        add_log(f"📢 [Stage 2] 1H HIGH ZONE | Stochastic K = {latest_k:.2f} -> รอสัญญาณ HIGH ZONE STAGE 3")
                        st.session_state.current_stage = 3
                    elif direction == "LOW" and latest_k < 15:
                        add_log(f"📢 [Stage 2] 1H LOW ZONE | Stochastic K = {latest_k:.2f} -> รอสัญญาณ LOW ZONE STAGE 3")
                        st.session_state.current_stage = 3
                        
            elif stage == 3:
                df_15m = fetch_data(period="5d", interval="15m")
                if df_15m is not None and not df_15m.empty:
                    k_15m, d_15m = calculate_stochastic(df_15m)
                    latest_k = float(k_15m.iloc[-1])
                    latest_d = float(d_15m.iloc[-1])
                    prev_k = float(k_15m.iloc[-2])
                    prev_d = float(d_15m.iloc[-2])
                    
                    is_bullish_cross = (prev_k < prev_d) and (latest_k > latest_d)
                    is_bearish_cross = (prev_k > prev_d) and (latest_k < latest_d)
                    
                    if direction == "HIGH" and latest_k > 80 and is_bearish_cross:
                        add_log(f"🔥 [Stage 3] 15M HIGH ZONE TRIGGER | K crosses down at {latest_k:.2f} -> ✅ ปิดรอบครบ 3 Stage! เริ่มรอบใหม่ Stage 1")
                        st.session_state.current_stage = 1
                        st.session_state.target_direction = "-"
                    elif direction == "LOW" and latest_k < 20 and is_bullish_cross:
                        add_log(f"🔥 [Stage 3] 15M LOW ZONE TRIGGER | K crosses up at {latest_k:.2f} -> ✅ ปิดรอบครบ 3 Stage! เริ่มรอบใหม่ Stage 1")
                        st.session_state.current_stage = 1
                        st.session_state.target_direction = "-"
                        
        except Exception as e:
            add_log(f"⚠️ Error in loop: {str(e)}")
            
        # ตรวจสอบทุกๆ 60 วินาที
        for _ in range(60):
            if st.session_state.bot_status != "Running":
                break
            time.sleep(1)

# ==========================================
# STREAMLIT UI
# ==========================================
st.title("🛡️ XAUUSD Zone Trigger Bot Dashboard")
st.markdown("ระบบเฝ้าระกราฟทองคำอัตโนมัติ 3 Stages (4H -> 1H -> 15M) รันบน Streamlit Cloud")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Bot Status", st.session_state.bot_status)
with col2:
    st.metric("Current Stage", f"Stage {st.session_state.current_stage}")
with col3:
    st.metric("Target Direction", st.session_state.target_direction)

st.divider()

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if st.button("▶️ Start Bot", use_container_width=True):
        if st.session_state.bot_status != "Running":
            t = threading.Thread(target=run_bot, daemon=True)
            t.start()
            st.rerun()
with col_btn2:
    if st.button("⏹️ Stop Bot", use_container_width=True):
        st.session_state.bot_status = "Stopped"
        add_log("🛑 Bot Stopped by user.")
        st.rerun()

st.subheader("📋 Real-Time Activity Logs")
log_container = st.container(height=400)
with log_container:
    for log in st.session_state.logs:
        st.text(log)
