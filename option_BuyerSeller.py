import streamlit as st
import requests
import pandas as pd
from datetime import datetime, time as dt_time
import time

# ----------------------------------------------------------
# Page Config
# ----------------------------------------------------------
st.set_page_config(layout="wide")
st.title("📈 NIFTY – 5 ATM Strike Premium Tracker (Always Showing Latest Prices)")

# ----------------------------------------------------------
# Auto-refresh every 5 minutes
# ----------------------------------------------------------
REFRESH_INTERVAL = 300  # seconds

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh >= REFRESH_INTERVAL:
    st.session_state.last_refresh = time.time()
    st.rerun()

# ----------------------------------------------------------
# Fetch Option Chain
# ----------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_option_chain():
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com"
    }
    try:
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=10)
        return resp.json()
    except:
        return None

# ----------------------------------------------------------
# ATM & 5 Strike Calculation
# ----------------------------------------------------------
def get_5_atm_strikes(spot):
    atm = round(spot / 50) * 50
    return [atm - 100, atm - 50, atm, atm + 50, atm + 100]

# ----------------------------------------------------------
# Storage for full-day multi-strike data
# ----------------------------------------------------------
if "multi_log" not in st.session_state:
    st.session_state.multi_log = []

# ----------------------------------------------------------
# Fetch data
# ----------------------------------------------------------
data = fetch_option_chain()
if not data:
    st.error("Could not fetch option chain (NSE blocking).")
    st.stop()

spot = data["records"]["underlyingValue"]
strikes = get_5_atm_strikes(spot)

st.subheader(f"🔵 Spot Price: {spot}")
st.write(f"Tracking 5 ATM strikes: {strikes}")

# Create map for quick lookup
oc_map = {item["strikePrice"]: item for item in data["records"]["data"]}

# ----------------------------------------------------------
# Always show latest fetched CE/PE values (even if market closed)
# ----------------------------------------------------------
latest_row = {"timestamp": datetime.now(), "spot": spot}

for strike in strikes:
    ce = oc_map.get(strike, {}).get("CE", {}).get("lastPrice", None)
    pe = oc_map.get(strike, {}).get("PE", {}).get("lastPrice", None)
    latest_row[f"CE_{strike}"] = ce
    latest_row[f"PE_{strike}"] = pe

st.write("### 📌 Latest CE/PE Prices (Live)")
st.dataframe(pd.DataFrame([latest_row]), use_container_width=True)

# ----------------------------------------------------------
# Log data during market hours ONLY
# ----------------------------------------------------------
now_time = datetime.now().time()
if dt_time(9, 15) <= now_time <= dt_time(15, 30):
    st.session_state.multi_log.append(latest_row)
else:
    st.info("📭 Market closed now — logging paused. Showing last available prices above.")

# ----------------------------------------------------------
# Show full-day logged data if any
# ----------------------------------------------------------
df = pd.DataFrame(st.session_state.multi_log)

if not df.empty:
    st.write("### 📄 Full-Day CE/PE Premium Data")
    st.dataframe(df, use_container_width=True)

    st.write("### 📉 Full-Day Premium Trend")
    chart_df = df.set_index("timestamp")[
        [f"CE_{s}" for s in strikes] + [f"PE_{s}" for s in strikes]
    ]
    st.line_chart(chart_df)

# ----------------------------------------------------------
# Decision Engine (only if enough data)
# ----------------------------------------------------------
if not df.empty:
    st.write("## 🔍 Decision Summary (All ATM Strikes)")

    def strike_decision(start_ce, end_ce, start_pe, end_pe):
        ce_trend = end_ce - start_ce
        pe_trend = end_pe - start_pe

        if ce_trend < 0 and pe_trend < 0:
            return "💰 Premium Decay → SELL Options"
        if ce_trend > 0 and pe_trend < 0:
            return "📈 Bullish → BUY CE"
        if pe_trend > 0 and ce_trend < 0:
            return "📉 Bearish → BUY PE"
        if ce_trend > 0 and pe_trend > 0:
            return "⚡ Volatility → BUY Straddle/Strangle"
        return "😐 Rangebound → Low Confidence"

    for strike in strikes:
        try:
            start_ce = df[f"CE_{strike}"].iloc[0]
            end_ce   = df[f"CE_{strike}"].iloc[-1]
            start_pe = df[f"PE_{strike}"].iloc[0]
            end_pe   = df[f"PE_{strike}"].iloc[-1]
            st.write(f"### Strike {strike}: {strike_decision(start_ce, end_ce, start_pe, end_pe)}")
        except:
            st.write(f"### Strike {strike}: Not enough data")

# ----------------------------------------------------------
# CSV Download
# ----------------------------------------------------------
if not df.empty:
    st.download_button(
        "⬇ Download 5-Strike Premium Data",
        df.to_csv(index=False),
        "nifty_5strike_premium_data.csv",
        "text/csv"
    )
