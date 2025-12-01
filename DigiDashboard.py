import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime, date
import pytz
import os

# -----------------------------------------------------
# TIMEZONE FIX
# -----------------------------------------------------
IST = pytz.timezone("Asia/Kolkata")

# -----------------------------------------------------
# STREAMLIT CONFIG
# -----------------------------------------------------
st.set_page_config(page_title="Combined Market Dashboard", layout="wide")

# -----------------------------------------------------
# AUTO REFRESH: EVERY 3 MINUTES
# -----------------------------------------------------
st_autorefresh(interval=180000, key="autorefresh")

# -----------------------------------------------------
# CREATE NSE SESSION
# -----------------------------------------------------
def get_nse_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        s.get("https://www.nseindia.com", timeout=5)
    except:
        pass
    return s

session = get_nse_session()

# -----------------------------------------------------
# STOCK DETAILS (SAFE VERSION)
# -----------------------------------------------------
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

        if last is None or openp is None:
            return None, None

        pct = ((last - openp) / openp) * 100 if openp else None
        return last, pct

    except:
        return None, None

# -----------------------------------------------------
# INDEX DETAILS (SAFE VERSION)
# -----------------------------------------------------
def get_index_details(index_name):
    try:
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=5).json()
        for idx in r["data"]:
            if idx["index"] == index_name:
                last = idx.get("last")
                openp = idx.get("open")
                if last is None or openp is None:
                    return None, None
                pct = ((last - openp) / openp) * 100 if openp else None
                return last, pct
    except:
        return None, None


def get_sensex_details():
    try:
        r = requests.get("https://api.bseindia.com/BseIndiaAPI/api/MktStat1/w", timeout=5).json()
        last = r["Sensex"].get("Curvalue")
        openp = r["Sensex"].get("Openvalue")
        if last is None or openp is None:
            return None, None
        pct = ((last - openp) / openp) * 100
        return last, pct
    except:
        return None, None


# -----------------------------------------------------
# TOP BANNER
# -----------------------------------------------------
st.title("📊 Combined Market Dashboard")
st.subheader("📌 Live Stock & Index Prices (Auto-refresh every 3 minutes)")

cols = st.columns(4)
i = 0

for name, symbol in STOCKS.items():
    last, pct = get_stock_details(symbol)
    if last is not None and pct is not None:
        cols[i].metric(name, f"₹{last}", f"{pct:+.2f}%")
    else:
        cols[i].metric(name, "N/A", "N/A")
    i = (i + 1) % 4

nifty, pct_nifty = get_index_details("NIFTY 50")
banknifty, pct_bank = get_index_details("NIFTY BANK")
sensex, pct_sensex = get_sensex_details()

cols = st.columns(3)

if nifty is not None and pct_nifty is not None:
    cols[0].metric("NIFTY 50", f"₹{nifty}", f"{pct_nifty:+.2f}%")
else:
    cols[0].metric("NIFTY 50", "N/A", "N/A")

if banknifty is not None and pct_bank is not None:
    cols[1].metric("BANKNIFTY", f"₹{banknifty}", f"{pct_bank:+.2f}%")
else:
    cols[1].metric("BANKNIFTY", "N/A", "N/A")

if sensex is not None and pct_sensex is not None:
    cols[2].metric("SENSEX", f"{sensex}", f"{pct_sensex:+.2f}%")
else:
    cols[2].metric("SENSEX", "N/A", "N/A")

st.markdown("---")

# -----------------------------------------------------
# OPTION MOMENTUM
# -----------------------------------------------------
st.header("📈 Option Momentum (ATM Normalized)")

def get_spot_price():
    try:
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=5).json()
        for idx in r["data"]:
            if idx["index"] == "NIFTY 50":
                return float(idx["last"])
    except:
        return None

def get_atm_strike(price, step=50):
    return int(round(price / step) * step)

def get_option_chain(symbol="NIFTY", strike=None):
    try:
        r = session.get(f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}", timeout=5).json()
        df = pd.json_normalize(r["records"]["data"])
        df.dropna(subset=["strikePrice"], inplace=True)
        row = df[df["strikePrice"] == strike]
        if row.empty:
            return None, None
        return row.iloc[0]["CE.lastPrice"], row.iloc[0]["PE.lastPrice"]
    except:
        return None, None


today = datetime.now(IST).date()
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
CSV_FILE = os.path.join(DATA_DIR, f"nifty_data_{today}.csv")

# ---------- FIXED: INITIALIZE SESSION STATE ----------
if "opt_history" not in st.session_state:
    if os.path.exists(CSV_FILE):
        st.session_state.opt_history = pd.read_csv(CSV_FILE, parse_dates=["time"]).to_dict("records")
    else:
        st.session_state.opt_history = []

if "open_spot" not in st.session_state:
    st.session_state.open_spot = None

if "open_ce" not in st.session_state:
    st.session_state.open_ce = None

if "open_pe" not in st.session_state:
    st.session_state.open_pe = None
# -----------------------------------------------------

def update_option_history():
    spot = get_spot_price()
    if spot is None:
        return

    atm = get_atm_strike(spot)
    ce, pe = get_option_chain("NIFTY", atm)
    if ce is None:
        return

    if st.session_state.open_spot is None:
        st.session_state.open_spot = spot
        st.session_state.open_ce = ce
        st.session_state.open_pe = pe

    spot_delta = spot - st.session_state.open_spot
    ce_delta = ce - st.session_state.open_ce
    pe_delta = pe - st.session_state.open_pe

    st.session_state.opt_history.append({
        "time": datetime.now(IST),     # FIXED TIMEZONE
        "spot_delta": spot_delta,
        "ce_delta": ce_delta,
        "pe_delta": pe_delta
    })

    pd.DataFrame(st.session_state.opt_history).to_csv(CSV_FILE, index=False)


# Auto update once per refresh
update_option_history()

df_opt = pd.DataFrame(st.session_state.opt_history)
if not df_opt.empty:
    st.line_chart(df_opt.set_index("time")[["spot_delta", "ce_delta", "pe_delta"]])
    st.dataframe(df_opt.tail(20))

st.markdown("---")

# -----------------------------------------------------
# OI TRACKER
# -----------------------------------------------------
st.header("📊 ATM 5 Strike OI Tracker")

OI_FILE = "oi_history_change.csv"

def load_oi_history():
    if os.path.exists(OI_FILE):
        df = pd.read_csv(OI_FILE)
        if df.empty or df["date"].iloc[-1] != str(today):
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
        if r.get("expiryDate") == expiry:
            ce = r.get("CE", {})
            pe = r.get("PE", {})
            rows.append({
                "strike": r["strikePrice"],
                "CE_change": ce.get("changeinOpenInterest", 0),
                "PE_change": pe.get("changeinOpenInterest", 0),
                "CE_OI": ce.get("openInterest", 0),
                "PE_OI": pe.get("openInterest", 0),
                "diff": abs(r["strikePrice"] - underlying)
            })

    df_atm = pd.DataFrame(rows).sort_values("diff").head(5)
    st.write("### ATM 5 OI Table")
    st.dataframe(df_atm)

    snap = {
        "date": str(today),
        "time": datetime.now(IST).strftime("%H:%M"),    # FIXED TIMEZONE
        "CE_change": df_atm["CE_change"].sum(),
        "PE_change": df_atm["PE_change"].sum(),
        "CE_OI_total": df_atm["CE_OI"].sum(),
        "PE_OI_total": df_atm["PE_OI"].sum()
    }

    oi_history = pd.concat([oi_history, pd.DataFrame([snap])], ignore_index=True)
    oi_history.to_csv(OI_FILE, index=False)

    st.metric("CE Change (ATM 5)", snap["CE_change"])
    st.metric("PE Change (ATM 5)", snap["PE_change"])

    # Change OI Chart
    if not oi_history.empty:
        st.write("### 📈 Change in OI (CE vs PE)")
        plt.figure(figsize=(10, 4))
        plt.plot(oi_history["time"], oi_history["CE_change"], marker='o', label="CE Change")
        plt.plot(oi_history["time"], oi_history["PE_change"], marker='o', label="PE Change")
        plt.grid(True)
        plt.legend()
        st.pyplot(plt)

    # Total OI Chart
    if "CE_OI_total" in oi_history.columns:
        st.write("### 📉 Total OI (CE vs PE)")
        plt.figure(figsize=(10, 4))
        plt.plot(oi_history["time"], oi_history["CE_OI_total"], marker='o', label="CE Total OI")
        plt.plot(oi_history["time"], oi_history["PE_OI_total"], marker='o', label="PE Total OI")
        plt.grid(True)
        plt.legend()
        st.pyplot(plt)
