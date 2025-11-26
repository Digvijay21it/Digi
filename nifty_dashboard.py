import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime, date
import os
import time

FILE = "oi_history_change.csv"

# --------------------------------------------
# Auto-refresh every 1 minute
# --------------------------------------------
def auto_refresh():
    st.experimental_set_query_params(t=int(time.time()))

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh > 60:
    st.session_state.last_refresh = time.time()
    auto_refresh()

# --------------------------------------------
# Fetch NSE data
# --------------------------------------------
def fetch_nse_option_chain():
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
    }
    s = requests.Session()
    s.headers.update(headers)
    s.get("https://www.nseindia.com")  # cookie init
    return s.get(url).json()

# --------------------------------------------
# Load or create history file
# --------------------------------------------
def load_history():
    if os.path.exists(FILE):
        df = pd.read_csv(FILE)
        # reset if date changed
        if df["date"].iloc[-1] != str(date.today()):
            return pd.DataFrame(columns=["date","time","CE_change","PE_change"])
        return df
    else:
        return pd.DataFrame(columns=["date","time","CE_change","PE_change"])

def save_history(df):
    df.to_csv(FILE, index=False)

# --------------------------------------------
# Streamlit UI
# --------------------------------------------
st.set_page_config(page_title="OI Tracker", layout="wide")
st.title("📊 ")
st.caption("Track Data")

# Load existing history
history_df = load_history()

# Fetch latest NSE data
try:
    data = fetch_nse_option_chain()
except:
    st.error("Failed to fetch NSE data.")
    st.stop()

records = data["records"]["data"]
expiry = data["records"]["expiryDates"][0]
underlying = data["records"]["underlyingValue"]

# Filter: current week expiry only
filtered = [r for r in records if r.get("expiryDate") == expiry]

# Build OI change table
rows = []
for r in filtered:
    ce = r.get("CE", {})
    pe = r.get("PE", {})

    rows.append({
        "strike": r["strikePrice"],
        "CE_change": ce.get("changeinOpenInterest", 0),
        "PE_change": pe.get("changeinOpenInterest", 0),
    })

df = pd.DataFrame(rows)
df["diff"] = abs(df["strike"] - underlying)

# Pick 5 ATM strikes only
df_atm = df.sort_values("diff").head(5)[["strike", "CE_change", "PE_change"]]

# --------------------------------------------
# Save new entry for today
# --------------------------------------------
current_time = datetime.now().strftime("%H:%M")
today = str(date.today())

snapshot = {
    "date": today,
    "time": current_time,
    "CE_change": df_atm["CE_change"].sum(),
    "PE_change": df_atm["PE_change"].sum()
}

# Only append if new minute
if len(history_df) == 0 or history_df["time"].iloc[-1] != current_time:
    history_df = pd.concat([history_df, pd.DataFrame([snapshot])], ignore_index=True)
    save_history(history_df)

# --------------------------------------------
# Display metrics
# --------------------------------------------
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Nifty Spot", underlying)

with col2:
    st.metric("Total CE Change (ATM 5)", snapshot["CE_change"])

with col3:
    st.metric("Total PE Change (ATM 5)", snapshot["PE_change"])

st.write("### ATM 5 Strike – Change in OI Table")
st.dataframe(df_atm)

# --------------------------------------------
# Plot full-day Change in OI Trend
# --------------------------------------------
st.write("### 📈 OI")

plt.figure(figsize=(12, 4))
plt.plot(history_df["time"], history_df["CE_change"], label="CE Change", color="blue", marker="o")
plt.plot(history_df["time"], history_df["PE_change"], label="PE Change", color="red", marker="o")
plt.xticks(rotation=45)
plt.grid(True)
plt.legend()
plt.tight_layout()

st.pyplot(plt)
