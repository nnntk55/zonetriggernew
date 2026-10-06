import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="ZONE TRIGGER // XAUUSD Live Auto",
    page_icon="⚡",
    layout="centered"
)

st.title("⚡ ZONE TRIGGER // XAUUSD Live Radar")
st.markdown(
    "ระบบสแกนสัญญาณ 3 ด่าน **4H ➔ 1H ➔ 15M** "
    "โดยใช้ XAUUSD จาก Yahoo Finance (`XAUUSD=X`) เป็นแหล่งข้อมูลเดียว"
)

# =========================================================
# CONSTANT
# =========================================================

YAHOO_SYMBOL = "XAUUSD=X"


# =========================================================
# SESSION STATE
# =========================================================

if "current_stage" not in st.session_state:
    st.session_state["current_stage"] = 1

if "active_direction" not in st.session_state:
    st.session_state["active_direction"] = None

if "last_stage_notification" not in st.session_state:
    st.session_state["last_stage_notification"] = None


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("⚙️ ตั้งค่าระบบ Telegram")

bot_token = st.sidebar.text_input(
    "Telegram Bot Token",
    type="password",
    placeholder="เช่น 123456789:ABCdef..."
)

chat_id = st.sidebar.text_input(
    "Telegram Chat ID",
    placeholder="เช่น 987654321"
)

st.sidebar.header("🔄 ควบคุมสถานะระบบ")

if st.sidebar.button("♻️ รีเซ็ตสถานะกลับไปด่าน 1"):

    st.session_state["current_stage"] = 1
    st.session_state["active_direction"] = None
    st.session_state["last_stage_notification"] = None

    st.sidebar.success(
        "รีเซ็ตสถานะเรียบร้อย เริ่มต้นใหม่ที่ด่าน 1"
    )


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(token, chat_id, message):

    if not token or not chat_id:
        return False, "กรุณากรอก Bot Token และ Chat ID"

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        if response.status_code == 200:
            return True, "ส่งข้อความสำเร็จ"

        return False, f"Telegram Error: {response.text}"

    except Exception as e:

        return False, str(e)


# =========================================================
# YAHOO XAUUSD DATA
# =========================================================

@st.cache_data(ttl=30)
def get_xauusd_intraday():

    """
    ดึง XAUUSD จาก Yahoo Finance เท่านั้น

    Symbol:
        XAUUSD=X

    ใช้ข้อมูล 15 นาทีเป็น Base timeframe
    แล้วนำไปสร้าง 1H / 4H จากข้อมูลชุดเดียวกัน
    """

    try:

        ticker = yf.Ticker(YAHOO_SYMBOL)

        df = ticker.history(
            period="30d",
            interval="15m",
            auto_adjust=False,
            prepost=False
        )

        if df is None or df.empty:
            raise ValueError(
                "Yahoo Finance ไม่ส่งข้อมูล XAUUSD กลับมา"
            )

        # รองรับ timezone
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)

        # กรณี yfinance ส่ง MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):

            df.columns = df.columns.get_level_values(0)

        required_columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        missing = [
            col for col in required_columns
            if col not in df.columns
        ]

        if missing:
            raise ValueError(
                f"ข้อมูล Yahoo ขาด column: {missing}"
            )

        df = df[required_columns].copy()

        df = df.dropna(
            subset=["Open", "High", "Low", "Close"]
        )

        if len(df) < 100:
            raise ValueError(
                f"ข้อมูลไม่เพียงพอ: {len(df)} candles"
            )

        return df

    except Exception as e:

        raise RuntimeError(
            f"ไม่สามารถดึง XAUUSD จาก Yahoo Finance ได้: {e}"
        )


# =========================================================
# GET CURRENT PRICE
# =========================================================

@st.cache_data(ttl=10)
def get_current_xauusd_price():

    try:

        ticker = yf.Ticker(YAHOO_SYMBOL)

        df = ticker.history(
            period="1d",
            interval="1m",
            auto_adjust=False,
            prepost=False
        )

        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna(subset=["Close"])

        if df.empty:
            return None

        price = float(df["Close"].iloc[-1])

        if price <= 0:
            return None

        return price

    except Exception:

        return None


# =========================================================
# RESAMPLE OHLC
# =========================================================

def resample_ohlc(df, timeframe):

    result = df.resample(timeframe).agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum"
    })

    return result.dropna(
        subset=["Open", "High", "Low", "Close"]
    )


# =========================================================
# STOCHASTIC
# =========================================================

def calculate_stochastic(
    df,
    period=14,
    smooth_k=3,
    smooth_d=3
):

    df = df.copy()

    lowest_low = (
        df["Low"]
        .rolling(window=period)
        .min()
    )

    highest_high = (
        df["High"]
        .rolling(window=period)
        .max()
    )

    denominator = highest_high - lowest_low

    raw_k = (
        100
        * (df["Close"] - lowest_low)
        / denominator
    )

    raw_k = raw_k.replace(
        [float("inf"), float("-inf")],
        pd.NA
    )

    k = raw_k.rolling(
        window=smooth_k
    ).mean()

    d = k.rolling(
        window=smooth_d
    ).mean()

    df["K"] = k
    df["D"] = d

    return df.dropna(
        subset=["K", "D"]
    )


# =========================================================
# SIDEBAR TEST TELEGRAM
# =========================================================

if st.sidebar.button(
    "🧪 ทดสอบส่งข้อความเข้า Telegram"
):

    success, msg = send_telegram(
        bot_token,
        chat_id,
        "⚡ *Test Alert*\n"
        "ZONE TRIGGER XAUUSD พร้อมทำงาน\n"
        "Feed: Yahoo Finance XAUUSD=X"
    )

    if success:
        st.sidebar.success(msg)
    else:
        st.sidebar.error(msg)


# =========================================================
# CURRENT PRICE DISPLAY
# =========================================================

current_price_display = get_current_xauusd_price()


st.markdown("---")

st.subheader(
    "🎯 สถานะเรดาร์ปัจจุบัน (State Machine)"
)

col1, col2, col3 = st.columns(3)

with col1:

    st.metric(
        "ด่านปัจจุบัน",
        f"Stage {st.session_state['current_stage']}"
    )

with col2:

    direction = st.session_state["active_direction"]

    st.metric(
        "ทิศทางเป้าหมาย",
        direction if direction else "รอสัญญาณด่าน 1"
    )

with col3:

    if current_price_display is not None:

        st.metric(
            "XAUUSD ราคา",
            f"{current_price_display:.2f} USD"
        )

    else:

        st.metric(
            "XAUUSD ราคา",
            "N/A"
        )


st.caption(
    "📡 Price Feed: Yahoo Finance — XAUUSD=X"
)


# =========================================================
# SCAN BUTTON
# =========================================================

if st.button(
    "🔍 กดสแกนกราฟและเช็กเงื่อนไขเรียลไทม์",
    type="primary"
):

    if not bot_token or not chat_id:

        st.error(
            "⚠ กรุณากรอก Telegram Bot Token "
            "และ Chat ID ที่ Sidebar ก่อน"
        )

        st.stop()

    with st.spinner(
        "กำลังดึง XAUUSD จาก Yahoo Finance..."
    ):

        try:

            # -------------------------------------------------
            # GET BASE DATA
            # -------------------------------------------------

            df_15m = get_xauusd_intraday()

            if df_15m.empty:

                raise ValueError(
                    "ไม่พบข้อมูล 15M"
                )

            # -------------------------------------------------
            # CURRENT PRICE
            # -------------------------------------------------

            current_price = get_current_xauusd_price()

            if current_price is None:

                # ใช้ close ล่าสุดจาก feed เดียวกัน
                current_price = float(
                    df_15m["Close"].iloc[-1]
                )

            # -------------------------------------------------
            # UPDATE LAST CANDLE
            # -------------------------------------------------
            #
            # สำคัญ:
            # ไม่ดึงราคาจาก GC=F
            # ทุกอย่างเป็น XAUUSD=X
            #

            df_15m = df_15m.copy()

            last_index = df_15m.index[-1]

            last_open = float(
                df_15m.loc[last_index, "Open"]
            )

            last_high = float(
                df_15m.loc[last_index, "High"]
            )

            last_low = float(
                df_15m.loc[last_index, "Low"]
            )

            df_15m.loc[last_index, "Close"] = current_price

            df_15m.loc[last_index, "High"] = max(
                last_high,
                current_price
            )

            df_15m.loc[last_index, "Low"] = min(
                last_low,
                current_price
            )

            # -------------------------------------------------
            # CREATE TIMEFRAMES FROM SAME SOURCE
            # -------------------------------------------------

            df_1h = resample_ohlc(
                df_15m,
                "1h"
            )

            df_4h = resample_ohlc(
                df_15m,
                "4h"
            )

            # -------------------------------------------------
            # INDICATORS
            # -------------------------------------------------

            df_4h_ind = calculate_stochastic(
                df_4h
            )

            df_1h_ind = calculate_stochastic(
                df_1h
            )

            df_15m_ind = calculate_stochastic(
                df_15m
            )

            if len(df_4h_ind) < 2:
                raise ValueError(
                    "ข้อมูล 4H ไม่เพียงพอสำหรับ Stochastic"
                )

            if len(df_1h_ind) < 2:
                raise ValueError(
                    "ข้อมูล 1H ไม่เพียงพอสำหรับ Stochastic"
                )

            if len(df_15m_ind) < 3:
                raise ValueError(
                    "ข้อมูล 15M ไม่เพียงพอสำหรับ Cross"
                )

            # -------------------------------------------------
            # CURRENT VALUES
            # -------------------------------------------------

            curr_4h = float(
                df_4h_ind["K"].iloc[-1]
            )

            curr_1h = float(
                df_1h_ind["K"].iloc[-1]
            )

            curr_15m = float(
                df_15m_ind["K"].iloc[-1]
            )

            prev_15m = float(
                df_15m_ind["K"].iloc[-2]
            )

            curr_d_15m = float(
                df_15m_ind["D"].iloc[-1]
            )

            prev_d_15m = float(
                df_15m_ind["D"].iloc[-2]
            )

            # -------------------------------------------------
            # DISPLAY
            # -------------------------------------------------

            st.success(
                f"✅ สแกนสำเร็จ | "
                f"XAUUSD = **{current_price:.2f} USD**"
            )

            st.write(
                f"📊 **Stochastic:** "
                f"4H K = **{curr_4h:.2f}** | "
                f"1H K = **{curr_1h:.2f}** | "
                f"15M K = **{curr_15m:.2f}**"
            )

            st.write(
                f"📈 15M: "
                f"K = **{curr_15m:.2f}**, "
                f"D = **{curr_d_15m:.2f}** | "
                f"Previous K = **{prev_15m:.2f}**, "
                f"Previous D = **{prev_d_15m:.2f}**"
            )

            # -------------------------------------------------
            # STATE
            # -------------------------------------------------

            stage = st.session_state[
                "current_stage"
            ]

            direction = st.session_state[
                "active_direction"
            ]

            # =================================================
            # STAGE 1
            # =================================================

            if stage == 1:

                # ---------------------------------------------
                # HIGH
                # ---------------------------------------------

                if curr_4h > 55:

                    st.session_state[
                        "current_stage"
                    ] = 2

                    st.session_state[
                        "active_direction"
                    ] = "HIGH"

                    msg = (
                        "🚨 *ZONE TRIGGER // XAUUSD*\n"
                        "🛡️ *[Stage 1]* "
                        "4H UP TO HIGH ZONE\n"
                        f"💰 ราคา: {current_price:.2f}\n"
                        f"4H K = {curr_4h:.2f}\n"
                        "👉 รอ Stage 2: "
                        "1H K > 85"
                    )

                    success, telegram_msg = send_telegram(
                        bot_token,
                        chat_id,
                        msg
                    )

                    if success:
                        st.success(
                            "🎯 ผ่าน Stage 1 ฝั่ง HIGH"
                        )
                    else:
                        st.warning(
                            f"ผ่าน Stage 1 แล้ว แต่ Telegram: "
                            f"{telegram_msg}"
                        )

                # ---------------------------------------------
                # LOW
                # ---------------------------------------------

                elif curr_4h < 45:

                    st.session_state[
                        "current_stage"
                    ] = 2

                    st.session_state[
                        "active_direction"
                    ] = "LOW"

                    msg = (
                        "🚨 *ZONE TRIGGER // XAUUSD*\n"
                        "📉 *[Stage 1]* "
                        "4H DOWN TO LOW ZONE\n"
                        f"💰 ราคา: {current_price:.2f}\n"
                        f"4H K = {curr_4h:.2f}\n"
                        "👉 รอ Stage 2: "
                        "1H K < 15"
                    )

                    success, telegram_msg = send_telegram(
                        bot_token,
                        chat_id,
                        msg
                    )

                    if success:
                        st.success(
                            "🎯 ผ่าน Stage 1 ฝั่ง LOW"
                        )
                    else:
                        st.warning(
                            f"ผ่าน Stage 1 แล้ว แต่ Telegram: "
                            f"{telegram_msg}"
                        )

                else:

                    st.warning(
                        f"⏳ Stage 1: "
                        f"4H K = {curr_4h:.2f} "
                        f"(ต้อง > 55 หรือ < 45)"
                    )

            # =================================================
            # STAGE 2
            # =================================================

            elif stage == 2:

                # ---------------------------------------------
                # HIGH
                # ---------------------------------------------

                if direction == "HIGH":

                    if curr_1h > 85:

                        st.session_state[
                            "current_stage"
                        ] = 3

                        msg = (
                            "🚨 *ZONE TRIGGER // XAUUSD*\n"
                            "⚡ *[Stage 2]* "
                            "1H HIGH ZONE\n"
                            f"💰 ราคา: {current_price:.2f}\n"
                            f"1H K = {curr_1h:.2f}\n"
                            "👉 รอ Stage 3: "
                            "15M Cross Above 80"
                        )

                        success, telegram_msg = send_telegram(
                            bot_token,
                            chat_id,
                            msg
                        )

                        if success:
                            st.success(
                                "🎯 ผ่าน Stage 2 ฝั่ง HIGH"
                            )
                        else:
                            st.warning(
                                f"ผ่าน Stage 2 แล้ว แต่ Telegram: "
                                f"{telegram_msg}"
                            )

                    else:

                        st.warning(
                            f"⏳ Stage 2 HIGH: "
                            f"1H K = {curr_1h:.2f} "
                            f"(ต้อง > 85)"
                        )

                # ---------------------------------------------
                # LOW
                # ---------------------------------------------

                elif direction == "LOW":

                    if curr_1h < 15:

                        st.session_state[
                            "current_stage"
                        ] = 3

                        msg = (
                            "🚨 *ZONE TRIGGER // XAUUSD*\n"
                            "⚡ *[Stage 2]* "
                            "1H LOW ZONE\n"
                            f"💰 ราคา: {current_price:.2f}\n"
                            f"1H K = {curr_1h:.2f}\n"
                            "👉 รอ Stage 3: "
                            "15M Cross Under 20"
                        )

                        success, telegram_msg = send_telegram(
                            bot_token,
                            chat_id,
                            msg
                        )

                        if success:
                            st.success(
                                "🎯 ผ่าน Stage 2 ฝั่ง LOW"
                            )
                        else:
                            st.warning(
                                f"ผ่าน Stage 2 แล้ว แต่ Telegram: "
                                f"{telegram_msg}"
                            )

                    else:

                        st.warning(
                            f"⏳ Stage 2 LOW: "
                            f"1H K = {curr_1h:.2f} "
                            f"(ต้อง < 15)"
                        )

            # =================================================
            # STAGE 3
            # =================================================

            elif stage == 3:

                # ---------------------------------------------
                # HIGH
                # ---------------------------------------------

                if direction == "HIGH":

                    is_cross_above_80 = (
                        curr_15m >= 80
                        and prev_15m <= prev_d_15m
                        and curr_15m > curr_d_15m
                    )

                    if is_cross_above_80:

                        msg = (
                            "🔥 *🚨 ZONE TRIGGER // XAUUSD*\n"
                            "🛑 *[Stage 3]* "
                            "15M HIGH ZONE TRIGGER\n"
                            f"💰 ราคา: {current_price:.2f}\n"
                            f"15M K = {curr_15m:.2f}\n"
                            f"15M D = {curr_d_15m:.2f}\n"
                            "🏁 *ปิดรอบสมบูรณ์!*\n"
                            "เริ่มรอบใหม่รอ Stage 1"
                        )

                        success, telegram_msg = send_telegram(
                            bot_token,
                            chat_id,
                            msg
                        )

                        st.success(
                            "🎯 ครบ 3 ด่านฝั่ง HIGH!"
                        )

                        st.session_state[
                            "current_stage"
                        ] = 1

                        st.session_state[
                            "active_direction"
                        ] = None

                    else:

                        st.warning(
                            f"⏳ Stage 3 HIGH: "
                            f"รอ 15M Cross Above 80 | "
                            f"K={curr_15m:.2f} | "
                            f"D={curr_d_15m:.2f}"
                        )

                # ---------------------------------------------
                # LOW
                # ---------------------------------------------

                elif direction == "LOW":

                    is_cross_under_20 = (
                        curr_15m <= 20
                        and prev_15m >= prev_d_15m
                        and curr_15m < curr_d_15m
                    )

                    if is_cross_under_20:

                        msg = (
                            "🔥 *🚨 ZONE TRIGGER // XAUUSD*\n"
                            "🛑 *[Stage 3]* "
                            "15M LOW ZONE TRIGGER\n"
                            f"💰 ราคา: {current_price:.2f}\n"
                            f"15M K = {curr_15m:.2f}\n"
                            f"15M D = {curr_d_15m:.2f}\n"
                            "🏁 *ปิดรอบสมบูรณ์!*\n"
                            "เริ่มรอบใหม่รอ Stage 1"
                        )

                        success, telegram_msg = send_telegram(
                            bot_token,
                            chat_id,
                            msg
                        )

                        st.success(
                            "🎯 ครบ 3 ด่านฝั่ง LOW!"
                        )

                        st.session_state[
                            "current_stage"
                        ] = 1

                        st.session_state[
                            "active_direction"
                        ] = None

                    else:

                        st.warning(
                            f"⏳ Stage 3 LOW: "
                            f"รอ 15M Cross Under 20 | "
                            f"K={curr_15m:.2f} | "
                            f"D={curr_d_15m:.2f}"
                        )

            # =================================================
            # DATA INFO
            # =================================================

            st.markdown("---")

            st.subheader("📡 ข้อมูล Feed")

            info_col1, info_col2 = st.columns(2)

            with info_col1:

                st.write(
                    f"**Symbol:** `{YAHOO_SYMBOL}`"
                )

                st.write(
                    "**Provider:** Yahoo Finance"
                )

            with info_col2:

                st.write(
                    f"**Candles 15M:** "
                    f"{len(df_15m):,}"
                )

                st.write(
                    f"**Last Update:** "
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

        except Exception as e:

            st.error(
                f"❌ เกิดข้อผิดพลาด: {e}"
            )

            st.info(
                "ระบบจะไม่ใช้ราคา fallback "
                "เพื่อป้องกันการส่งสัญญาณจากราคาที่ไม่ใช่ตลาดจริง"
            )


# =========================================================
# FOOTER
# =========================================================

st.markdown("---")

st.markdown(
    """
💡 **ระบบปัจจุบัน**

- 🟡 Feed: `XAUUSD=X`
- 📊 Base timeframe: 15M
- ⏱️ สร้าง 1H และ 4H จากข้อมูลชุดเดียวกัน
- 📈 Indicator: Stochastic K/D
- 🚦 State Machine: Stage 1 → Stage 2 → Stage 3
- 📲 Telegram Alert
- 🚫 ไม่มี `GC=F`
- 🚫 ไม่มีราคา fallback `4161.00`

⚠️ **หมายเหตุ:** ราคา Yahoo Finance อาจยังไม่ตรงกับราคา XAUUSD ของ Exness/TradingView แบบ tick-by-tick เพราะเป็นคนละ market-data feed
"""
)

