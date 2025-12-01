import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime
import pytz
import os

# ---------------- TIMEZONE ----------------
IST = pytz.timezone("Asia/Kolkata")

# ---------------- STREAMLIT CONFIG ----------------
st.set_page_config(page_title="Combined Market Dashboard", layout="wide")
st_autorefresh(interval=180000, key="autorefresh")  # Refresh every 3 minutes

# ---------------- NSE SESSION ----------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
})

# ---------------- STOCKS ----------------
STOCKS = {
    "Reliance": "RELIANCE",
    "HDFC Bank": "HDFCBANK",
    "Bharti Airtel": "BHARTIARTL",
    "TCS": "TCS",
    "ICICI Bank": "ICICIBANK",
    "SBI": "SBIN",
    "Infosys": "INFY",
}

def get_stock_details(symbol):
    try:
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        res = session.get(url, timeout=5).json()
        last = res["priceInfo"].get("lastPrice")
        openp = res["priceInfo"].get("open")
        pct = ((last - openp)/openp*100) if last and openp else None
        return last, pct
    except:
        return None, None

def get_index_details(index_name):
    try:
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=5).json()
        for idx in r["data"]:
            if idx["index"] == index_name:
                last = idx.get("last")
                openp = idx.get("open")
                pct = ((last - openp)/openp*100) if last and openp else None
                return last, pct
    except:
        return None, None

def get_sensex_details():
    try:
        r = requests.get("https://api.bseindia.com/BseIndiaAPI/api/MktStat1/w", timeout=5).json()
        last = r["Sensex"].get("Curvalue")
        openp = r["Sensex"].get("Openvalue")
        pct = ((last - openp)/openp*100) if last and openp else None
        return last, pct
    except:
        return None, None

# ---------------- TOP BANNER ----------------
st.title("📊 Combined Market Dashboard")
st.subheader("📌 Live Stock & Index Prices (Auto-refresh every 3 minutes)")

cols = st.columns(4)
i = 0
for name, symbol in STOCKS.items():
    last, pct = get_stock_details(symbol)
    cols[i].metric(name, f"₹{last}" if last else "N/A", f"{pct:+.2f}%" if pct else "N/A")
    i = (i+1)%4

nifty, pct_nifty = get_index_details("NIFTY 50")
banknifty, pct_bank = get_index_details("NIFTY BANK")
sensex, pct_sensex = get_sensex_details()

cols = st.columns(3)
cols[0].metric("NIFTY 50", f"₹{nifty}" if nifty else "N/A", f"{pct_nifty:+.2f}%" if pct_nifty else "N/A")
cols[1].metric("BANKNIFTY", f"₹{banknifty}" if banknifty else "N/A", f"{pct_bank:+.2f}%" if pct_bank else "N/A")
cols[2].metric("SENSEX", f"{sensex}" if sensex else "N/A", f"{pct_sensex:+.2f}%" if pct_sensex else "N/A")

st.markdown("---")

# ====================================================================
#          🔥 REPLACED SECTION — NEW ATM COMPARISON LOGIC
# ====================================================================
st.header("📈 ATM Normalized Movement (NIFTY vs CE vs PE)")

today = datetime.now(IST).date()
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
CSV_FILE_ATM = os.path.join(DATA_DIR, f"atm_compare_{today}.csv")

# -------- Get ATM Strike Details --------
def get_atm_prices():
    try:
        url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        data = session.get(url, timeout=5).json()

        underlying = data["records"]["underlyingValue"]
        expiry = data["records"]["expiryDates"][0]

        atm_strike = int(round(underlying / 50) * 50)

        for r in data["records"]["data"]:
            if r.get("strikePrice") == atm_strike and r.get("expiryDate") == expiry:
                return underlying, r["CE"]["lastPrice"], r["PE"]["lastPrice"]
        return None, None, None

    except:
        return None, None, None

# -------- Update intraday history --------
def update_atm_history():
    now = datetime.now(IST)

    # Market hours only
    if not (now.hour >= 9 and (now.hour < 15 or (now.hour == 15 and now.minute <= 30))):
        return pd.DataFrame()

    underlying, ce, pe = get_atm_prices()
    if underlying is None:
        return pd.DataFrame()

    entry = {
        "time": now,
        "NIFTY": underlying,
        "CE": ce,
        "PE": pe
    }

    if os.path.exists(CSV_FILE_ATM):
        df = pd.read_csv(CSV_FILE_ATM, parse_dates=["time"])
        df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    else:
        df = pd.DataFrame([entry])

    df.to_csv(CSV_FILE_ATM, index=False)
    return df

df_atm = update_atm_history()

if df_atm.empty:
    st.warning("Waiting for market time or unable to fetch ATM data.")
else:
    # ---- Normalize to 0 at 9:15 ----
    df_norm = df_atm.copy()

    base_n = df_norm["NIFTY"].iloc[0]
    base_ce = df_norm["CE"].iloc[0]
    base_pe = df_norm["PE"].iloc[0]

    df_norm["NIFTY_norm"] = (df_norm["NIFTY"] - base_n).abs()
    df_norm["CE_norm"] = (df_norm["CE"] - base_ce).abs()
    df_norm["PE_norm"] = (df_norm["PE"] - base_pe).abs()

    st.subheader("📉 Normalized Movement from 9:15 AM (Positive Movement Only)")

    st.line_chart(
        df_norm.set_index("time")[["NIFTY_norm", "CE_norm", "PE_norm"]]
    )

    latest = df_norm.iloc[-1]
    col = st.columns(3)
    col[0].metric("NIFTY Movement", f"{latest['NIFTY_norm']:.2f}")
    col[1].metric("ATM CE Movement", f"{latest['CE_norm']:.2f}")
    col[2].metric("ATM PE Movement", f"{latest['PE_norm']:.2f}")

st.markdown("---")

# ====================================================================
#                     ORIGINAL OI TRACKER BELOW (UNTOUCHED)
# ====================================================================
st.header("📊 ATM 5 Strike OI Tracker")
OI_FILE = "oi_history_change.csv"

def load_oi_history():
    if os.path.exists(OI_FILE):
        df = pd.read_csv(OI_FILE)
        if df.empty or df["date"].iloc[-1]!=str(today):
            return pd.DataFrame(columns=["date","time","CE_change","PE_change","CE_OI_total","PE_OI_total"])
        return df
    return pd.DataFrame(columns=[])

oi_history = load_oi_history()

def fetch_oi():
    try:
        return session.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", timeout=5).json()
    except:
        return None

data_oi = fetch_oi()
if data_oi:
    records = data_oi["records"]["data"]
    expiry = data_oi["records"]["expiryDates"][0]
    underlying = data_oi["records"]["underlyingValue"]

    rows = []
    for r in records:
        if r.get("expiryDate")==expiry and r.get("CE") and r.get("PE"):
            ce = r.get("CE",{})
            pe = r.get("PE",{})
            rows.append({
                "strike": r["strikePrice"],
                "CE_change": ce.get("changeinOpenInterest",0),
                "PE_change": pe.get("changeinOpenInterest",0),
                "CE_OI": ce.get("openInterest",0),
                "PE_OI": pe.get("openInterest",0),
                "diff": abs(r["strikePrice"]-underlying)
            })
    df_atm = pd.DataFrame(rows).sort_values("diff").head(5)
    st.write("### ATM 5 OI Table")
    st.dataframe(df_atm)

    snap = {
        "date": str(today),
        "time": datetime.now(IST).strftime("%H:%M"),
        "CE_change": df_atm["CE_change"].sum(),
        "PE_change": df_atm["PE_change"].sum(),
        "CE_OI_total": df_atm["CE_OI"].sum(),
        "PE_OI_total": df_atm["PE_OI"].sum()
    }

    oi_history = pd.concat([oi_history, pd.DataFrame([snap])], ignore_index=True)
    oi_history.to_csv(OI_FILE, index=False)

    st.metric("CE Change (ATM 5)", snap["CE_change"])
    st.metric("PE Change (ATM 5)", snap["PE_change"])

    if not oi_history.empty:
        st.write("### 📈 Change in OI (CE vs PE)")
        plt.figure(figsize=(10,4))
        plt.plot(oi_history["time"], oi_history["CE_change"], marker='o', label="CE Change")
        plt.plot(oi_history["time"], oi_history["PE_change"], marker='o', label="PE Change")
        plt.grid(True)
        plt.legend()
        st.pyplot(plt)

        st.write("### 📉 Total OI (CE vs PE)")
        plt.figure(figsize=(10,4))
        plt.plot(oi_history["time"], oi_history["CE_OI_total"], marker='o', label="CE Total OI")
        plt.plot(oi_history["time"], oi_history["PE_OI_total"], marker='o', label="PE Total OI")
        plt.grid(True)
        plt.legend()
        st.pyplot(plt)
