import streamlit as st 
import pandas as pd
import matplotlib.pyplot as plt
import requests
from bs4 import BeautifulSoup
from datetime import datetime, time as dt_time, date
from zoneinfo import ZoneInfo
import os
import time

# -----------------------------------
# Configuration
# -----------------------------------
FILE = "oi_history_change.csv"
TIMEZONE = ZoneInfo("Asia/Kolkata")
AUTO_REFRESH_INTERVAL = 180  # 3 minutes

st.set_page_config(page_title="Digi OI Tracker", layout="wide")
st.title("📊 Digi OI Tracker")
st.caption("Track ATM 5 Strike OI & OI Change (Auto-refresh every 3 min, HTML fallback enabled)")

# -----------------------------------
# LOAD HISTORY
# -----------------------------------
def load_history():
    if os.path.exists(FILE):
        df = pd.read_csv(FILE)
        if df.empty:
            return pd.DataFrame(columns=["date","time","CE_change","PE_change","CE_OI_total","PE_OI_total"])
        if df["date"].iloc[-1] != str(date.today()):
            return pd.DataFrame(columns=["date","time","CE_change","PE_change","CE_OI_total","PE_OI_total"])
        return df
    return pd.DataFrame(columns=["date","time","CE_change","PE_change","CE_OI_total","PE_OI_total"])

def save_history(df):
    df.to_csv(FILE, index=False)

history_df = load_history()

# -----------------------------------
# CURRENT TIME
# -----------------------------------
now = datetime.now(TIMEZONE)
st.write("Current time (IST):", now.strftime("%Y-%m-%d %H:%M:%S"))

# Market hours
market_start = dt_time(9, 10)
market_end = dt_time(16, 0)
is_market_open = market_start <= now.time() <= market_end

# -----------------------------------
# LIVE MARKET SENTIMENT AT TOP
# -----------------------------------
if history_df.empty:
    st.info("Market sentiment will appear here once data is loaded.")
else:
    last_snapshot = history_df.iloc[-1]
    CE_change = last_snapshot["CE_change"]
    PE_change = last_snapshot["PE_change"]
    
    # Calculate percentage difference safely
    total_change = abs(CE_change) + abs(PE_change)
    if total_change != 0:
        CE_pct = round(CE_change / total_change * 100, 2)
        PE_pct = round(PE_change / total_change * 100, 2)
    else:
        CE_pct = PE_pct = 0
    
    # Market sentiment message
    if CE_change > PE_change:
        sentiment_msg = f"🚀 Market Sentiment: BULLISH / UP-SIDE\nCE: {CE_change} ({CE_pct}%), PE: {PE_change} ({PE_pct}%)"
        st.success(sentiment_msg)
    else:
        sentiment_msg = f"🐻 Market Sentiment: BEARISH / DOWN-SIDE\nCE: {CE_change} ({CE_pct}%), PE: {PE_change} ({PE_pct}%)"
        st.error(sentiment_msg)
    
    # How much data captured today
    captured_points = len(history_df)
    st.info(f"📊 Data points captured today: {captured_points}")

# -----------------------------------
# Auto refresh
# -----------------------------------
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh > AUTO_REFRESH_INTERVAL:
    st.session_state.last_refresh = time.time()
    st.experimental_rerun()

# -----------------------------------
# NSE API fetch
# -----------------------------------
def fetch_api():
    try:
        url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        headers = {"User-Agent": "Mozilla/5.0"}
        s = requests.Session()
        s.headers.update(headers)
        s.get("https://www.nseindia.com", timeout=5)
        return s.get(url, timeout=5).json()
    except:
        return None

# -----------------------------------
# NSE HTML fallback fetch
# -----------------------------------
def fetch_html():
    try:
        url = "https://www.nseindia.com/option-chain"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")

        table = soup.find("table")
        if table is None:
            return None

        df = pd.read_html(str(table))[0]
        return df
    except:
        return None

# -----------------------------------
# Attempt to fetch API → else HTML fallback
# -----------------------------------
data = fetch_api()

if data and "records" in data:
    source = "API"
elif (html_df := fetch_html()) is not None:
    data = html_df
    source = "HTML"
else:
    data = None
    source = None

# -----------------------------------
# If NO DATA from anywhere → show last saved
# -----------------------------------
if data is None:
    st.error("No live data available (API + HTML failed)")
    if not history_df.empty:
        st.info("Showing last saved data:")
        st.json(history_df.iloc[-1].to_dict())
    else:
        st.warning("No saved data available for today.")
    st.stop()

# -----------------------------------
# PROCESS DATA
# -----------------------------------
if source == "API":
    st.success("Live data received from API")

    records = data["records"]["data"]
    expiry = data["records"]["expiryDates"][0]
    underlying = data["records"]["underlyingValue"]

    filtered = [r for r in records if r.get("expiryDate") == expiry]

    rows = []
    for r in filtered:
        ce = r.get("CE", {})
        pe = r.get("PE", {})
        rows.append({
            "strike": r["strikePrice"],
            "CE_change": ce.get("changeinOpenInterest", 0),
            "PE_change": pe.get("changeinOpenInterest", 0),
            "CE_OI": ce.get("openInterest", 0),
            "PE_OI": pe.get("openInterest", 0)
        })

    df = pd.DataFrame(rows)
    df["diff"] = abs(df["strike"] - underlying)
    df_atm = df.sort_values("diff").head(5)

elif source == "HTML":
    st.success("Data received from NSE HTML fallback (EOD supported)")
    df = data

    df.columns = df.columns.droplevel() if isinstance(df.columns, pd.MultiIndex) else df.columns
    df = df.rename(columns={
        "Strike Price": "strike",
        "CE Change in OI": "CE_change",
        "PE Change in OI": "PE_change",
        "CE OI": "CE_OI",
        "PE OI": "PE_OI"
    })

    df = df.dropna(subset=["strike"])
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df = df.dropna(subset=["strike"])

    underlying = df["strike"].median()
    df["diff"] = abs(df["strike"] - underlying)
    df_atm = df.sort_values("diff").head(5)

# -----------------------------------
# SAVE SNAPSHOT (ONLY DURING MARKET HOURS)
# -----------------------------------
current_time = now.strftime("%H:%M")
today = str(now.date())

snapshot = {
    "date": today,
    "time": current_time,
    "CE_change": df_atm["CE_change"].sum(),
    "PE_change": df_atm["PE_change"].sum(),
    "CE_OI_total": df_atm["CE_OI"].sum(),
    "PE_OI_total": df_atm["PE_OI"].sum()
}

if is_market_open:
    if history_df.empty or history_df["time"].iloc[-1] != current_time:
        history_df = pd.concat([history_df, pd.DataFrame([snapshot])], ignore_index=True)
        save_history(history_df)

# -----------------------------------
# SHOW METRICS
# -----------------------------------
col1, col2, col3 = st.columns(3)
with col1: st.metric("CE Change (ATM 5)", snapshot["CE_change"])
with col2: st.metric("PE Change (ATM 5)", snapshot["PE_change"])
with col3: st.metric("Data Source", source)

st.write("### ATM 5 Strikes OI Table")
st.dataframe(df_atm, use_container_width=True)

# -----------------------------------
# PLOTS: CHANGE IN OI + TOTAL OI
# -----------------------------------
if not history_df.empty:

    # ---- CHANGE IN OI ----
    st.write("### 📈 Change in OI (CE vs PE)")
    plt.figure(figsize=(12, 4))
    plt.plot(history_df["time"], history_df["CE_change"], label="CE Change", color="blue", marker='o')
    plt.plot(history_df["time"], history_df["PE_change"], label="PE Change", color="red", marker='o')
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt)

    # ---- TOTAL OI ----
    if "CE_OI_total" in history_df.columns and "PE_OI_total" in history_df.columns:
        st.write("### 📉 Total OI (CE vs PE)")
        plt.figure(figsize=(12, 4))
        plt.plot(history_df["time"], history_df["CE_OI_total"], label="CE Total OI", color="purple", marker='o')
        plt.plot(history_df["time"], history_df["PE_OI_total"], label="PE Total OI", color="green", marker='o')
        plt.xticks(rotation=45)
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        st.pyplot(plt)
