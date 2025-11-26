import streamlit as st
import pandas as pd
import requests
import time
import datetime

# -------------------------------------------------
# NSE Session Setup
# -------------------------------------------------
def get_nse_session():
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json",
    }
    session.headers.update(headers)
    session.get("https://www.nseindia.com", timeout=5)
    return session

session = get_nse_session()

# -------------------------------------------------
# Fetch Functions
# -------------------------------------------------
def get_spot_price(symbol="NIFTY 50"):
    try:
        r = session.get("https://www.nseindia.com/api/allIndices", timeout=5)
        data = r.json()

        for item in data["data"]:
            if item["index"] == symbol:
                return float(item["last"])
        return None
    except:
        return None

def get_option_chain(symbol="NIFTY", strike=None):
    try:
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        r = session.get(url, timeout=5)
        data = r.json()

        df = pd.json_normalize(data["records"]["data"])
        df = df.dropna(subset=["strikePrice"])

        row = df[df["strikePrice"] == strike]
        if row.empty:
            return None, None

        return row.iloc[0]["CE.lastPrice"], row.iloc[0]["PE.lastPrice"]
    except:
        return None, None

def get_atm_strike(spot, step=50):
    return int(round(spot / step) * step)

# -------------------------------------------------
# Streamlit Config
# -------------------------------------------------
st.set_page_config(page_title="Option Momentum Dashboard", layout="wide")
st.title("📈 ATM Options Momentum (Normalized to 0 at Day Start)")

# Auto-refresh = 30 sec (default)
refresh_rate = st.sidebar.slider("Refresh interval (seconds)", 5, 60, 30)

placeholder = st.empty()

if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.open_spot = None
    st.session_state.open_ce = None
    st.session_state.open_pe = None

# -------------------------------------------------
# Market Timings
# -------------------------------------------------
market_start = datetime.time(9, 10)
market_end   = datetime.time(15, 45)

# -------------------------------------------------
# Live Loop
# -------------------------------------------------
while True:

    now = datetime.datetime.now().time()

    # -------------------------------------
    # Market Timing Check
    # -------------------------------------
    if not (market_start <= now <= market_end):
        with placeholder.container():
            st.warning("⏳ Market is closed. Live updates resume at **9:10 AM**.")
        time.sleep(refresh_rate)
        continue  # stop updating until market reopens

    # When within market hours → fetch data
    spot = get_spot_price()
    if spot is None:
        st.error("Failed to fetch Spot… reconnecting to NSE")
        session = get_nse_session()
        time.sleep(refresh_rate)
        continue

    atm = get_atm_strike(spot)
    ce, pe = get_option_chain("NIFTY", atm)

    if ce is None:
        st.error("Failed to fetch option chain… reconnecting")
        session = get_nse_session()
        time.sleep(refresh_rate)
        continue

    # Initialization at first tick
    if st.session_state.open_spot is None:
        st.session_state.open_spot = spot
        st.session_state.open_ce = ce
        st.session_state.open_pe = pe

    # Normalized changes
    spot_delta = spot - st.session_state.open_spot
    ce_delta = ce - st.session_state.open_ce
    pe_delta = pe - st.session_state.open_pe

    # Real delta (momentum ratios)
    if len(st.session_state.history) > 1:
        prev = st.session_state.history[-1]
        s_chg = spot_delta - prev["spot_delta"]
        c_chg = ce_delta - prev["ce_delta"]
        p_chg = pe_delta - prev["pe_delta"]

        real_delta_ce = c_chg / s_chg if s_chg != 0 else 0
        real_delta_pe = p_chg / s_chg if s_chg != 0 else 0
    else:
        real_delta_ce = 0
        real_delta_pe = 0

    # Store values for chart/table
    st.session_state.history.append({
        "time": datetime.datetime.now(),
        "spot_delta": spot_delta,
        "ce_delta": ce_delta,
        "pe_delta": pe_delta,
        "real_delta_ce": real_delta_ce,
        "real_delta_pe": real_delta_pe
    })

    df = pd.DataFrame(st.session_state.history)

    # -------------------------------------------------
    # UI Display
    # -------------------------------------------------
    with placeholder.container():

        st.subheader(f"ATM Strike: {atm}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Spot", f"{spot:.2f}", f"{spot_delta:+.2f}")
        col2.metric("CE", f"{ce:.2f}", f"{ce_delta:+.2f}")
        col3.metric("PE", f"{pe:.2f}", f"{pe_delta:+.2f}")

        st.subheader("🧭 Normalized Momentum Chart (Start = 0)")
        st.line_chart(
            df.set_index("time")[["spot_delta", "ce_delta", "pe_delta"]]
        )

        st.subheader("📌 Real Momentum Ratio (Option vs Spot Movement)")
        col4, col5 = st.columns(2)
        col4.metric("CE Real Delta", f"{real_delta_ce:.2f}")
        col5.metric("PE Real Delta", f"{real_delta_pe:.2f}")

        st.dataframe(df.tail(20))

    time.sleep(refresh_rate)
