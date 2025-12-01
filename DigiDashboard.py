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

# ---------------- ATM 5 CE/PE PREMIUMS ----------------
st.header("📈 ATM 5 CE/PE Premiums (Current Week)")

today = datetime.now(IST).date()
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
CSV_FILE = os.path.join(DATA_DIR, f"atm5_premiums_{today}.csv")

def get_spot_price():
    try:
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=5).json()
        for idx in r["data"]:
            if idx["index"] == "NIFTY 50":
                return float(idx["last"])
    except:
        return None

def get_atm_5_premiums(symbol="NIFTY"):
    spot = get_spot_price()
    if spot is None:
        return []
    try:
        data = session.get(f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}", timeout=5).json()
        records = data["records"]["data"]
        expiry = data["records"]["expiryDates"][0]

        rows = [r for r in records if r.get("expiryDate")==expiry and r.get("CE") and r.get("PE")]
        atm_strike = int(round(spot/50)*50)
        rows.sort(key=lambda x: abs(x["strikePrice"]-atm_strike))
        atm_5 = rows[:5]

        premiums = []
        for r in atm_5:
            premiums.append({
                "time": datetime.now(IST),
                "strike": r["strikePrice"],
                "CE": r["CE"]["lastPrice"],
                "PE": r["PE"]["lastPrice"]
            })
        return premiums
    except:
        return []

def update_premium_history():
    atm_5 = get_atm_5_premiums()
    if not atm_5:
        return pd.DataFrame()
    df = pd.DataFrame(atm_5)
    if os.path.exists(CSV_FILE):
        df_history = pd.read_csv(CSV_FILE, parse_dates=["time"])
        df = pd.concat([df_history, df], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)
    return df

# Update and display
spot_price = get_spot_price()
if spot_price:
    st.metric("NIFTY 50 Spot Price", f"₹{spot_price}")

df_history = update_premium_history()

if df_history.empty:
    st.write("Failed to fetch option chain data.")
else:
    latest = df_history.groupby("strike").last().reset_index()
    st.subheader("📌 Latest ATM 5 CE/PE Premiums")
    st.dataframe(latest[["strike","CE","PE"]])

    st.subheader("📈 CE vs PE Premium Movement (ATM 5)")
    plt.figure(figsize=(12,5))
    for strike in latest["strike"]:
        df_strike = df_history[df_history["strike"]==strike]
        plt.plot(df_strike["time"], df_strike["CE"], label=f"CE {strike}", marker='o')
        plt.plot(df_strike["time"], df_strike["PE"], label=f"PE {strike}", marker='x')
    plt.xlabel("Time")
    plt.ylabel("Premium (₹)")
    plt.title("ATM 5 CE/PE Premiums Over Time")
    plt.legend()
    plt.grid(True)
    st.pyplot(plt)

st.markdown("---")

# ---------------- OI TRACKER (Original Code) ----------------
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
