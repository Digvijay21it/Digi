import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime, date
import pytz
import os

# ------------------------------  
# TIMEZONE
# ------------------------------
IST = pytz.timezone("Asia/Kolkata")

# ------------------------------  
# STREAMLIT CONFIG
# ------------------------------
st.set_page_config(page_title="Combined Market Dashboard", layout="wide")
st_autorefresh(interval=180000, key="autorefresh")  # refresh every 3 minutes

# ------------------------------  
# NSE SESSION
# ------------------------------
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

# ------------------------------  
# SPOT PRICE
# ------------------------------
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

# ------------------------------  
# SAFE OPTION CHAIN
# ------------------------------
def safe_price(opt):
    if opt is None:
        return None
    return (
        opt.get("lastPrice")
        or opt.get("closePrice")
        or opt.get("bidprice")
        or opt.get("askPrice")
    )

def get_option_chain(symbol="NIFTY", strike=None):
    try:
        r = session.get(
            f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}",
            timeout=5,
        ).json()
        rows = r["records"]["data"]
        for r in rows:
            if r.get("strikePrice") == strike:
                ce = safe_price(r.get("CE"))
                pe = safe_price(r.get("PE"))
                return ce, pe
        return None, None
    except:
        return None, None

# ------------------------------  
# DATA STORAGE
# ------------------------------
today = datetime.now(IST).date()
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
CSV_FILE = os.path.join(DATA_DIR, f"nifty_data_{today}.csv")

# Initialize session state
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

# ------------------------------  
# UPDATE OPTION HISTORY
# ------------------------------
def update_option_history():
    spot = get_spot_price()
    if spot is None:
        return

    atm = get_atm_strike(spot)
    ce, pe = get_option_chain("NIFTY", atm)
    if ce is None or pe is None:
        return

    # Initialize open values if first run
    if st.session_state.open_spot is None:
        st.session_state.open_spot = spot
        st.session_state.open_ce = ce
        st.session_state.open_pe = pe

    # Calculate deltas
    spot_delta = spot - st.session_state.open_spot
    ce_delta = ce - st.session_state.open_ce
    pe_delta = pe - st.session_state.open_pe

    # Append to history
    st.session_state.opt_history.append({
        "time": datetime.now(IST),
        "spot_delta": spot_delta,
        "ce_delta": ce_delta,
        "pe_delta": pe_delta
    })

    # Save CSV
    pd.DataFrame(st.session_state.opt_history).to_csv(CSV_FILE, index=False)

# Auto-update
update_option_history()

# ------------------------------  
# DISPLAY CHART AND TABLE
# ------------------------------
st.header("📈 Option Momentum (ATM Normalized)")

df_opt = pd.DataFrame(st.session_state.opt_history)
if not df_opt.empty:
    st.line_chart(df_opt.set_index("time")[["spot_delta", "ce_delta", "pe_delta"]])
    st.dataframe(df_opt.tail(20))
