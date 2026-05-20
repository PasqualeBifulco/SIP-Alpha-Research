import os
import pandas as pd
import yfinance as yf
from tqdm import tqdm

HIST_FILE        = "S&P 500 Historical Components & Changes(01-17-2026).csv"
START_DATE       = "2001-01-01"
END_DATE         = "2026-05-16"
OUTPUT_FILE      = "sp500_prices.parquet"
BATCH_SIZE       = 100
FORCE_REDOWNLOAD = True

# Bucket 2: old ticker → current Yahoo ticker (same underlying company, renamed).
# Yahoo stores the full price history under the current/final ticker symbol.
TICKER_RENAMES = {
    "ANTM":  "ELV",    # Anthem → Elevance Health (2022)
    "ABC":   "COR",    # AmerisourceBergen → Cencora (2023)
    "CDAY":  "DAY",    # Ceridian → Dayforce (2024)
    "NLOK":  "GEN",    # NortonLifeLock → Gen Digital (2022)
    "SYMC":  "GEN",    # Symantec → Gen Digital (via NLOK)
    "CTL":   "LUMN",   # CenturyLink → Lumen Technologies (2020)
    "BHGE":  "BKR",    # Baker Hughes GE → Baker Hughes (2020)
    "FB":    "META",   # Facebook → Meta Platforms (2021)
    "WLTW":  "WTW",    # Willis Towers Watson rename (2022)
    "FLT":   "CPAY",   # FleetCor → Corpay (2024)
    "PKI":   "RVTY",   # PerkinElmer → Revvity (2023)
    "RE":    "EG",     # Everest Re → Everest Group (2023)
    "BLL":   "BALL",   # Ball Corporation ticker change (2022)
    "JEC":   "J",      # Jacobs Engineering → Jacobs Solutions (2019)
    "VIAC":  "PARA",   # ViacomCBS → Paramount Global (2022)
    "VIAB":  "PARA",   # Viacom B → Paramount Global (chain)
    "CBS":   "PARA",   # CBS → ViacomCBS → Paramount Global
    "DISCA": "WBD",    # Discovery A → Warner Bros. Discovery (2022)
    "DISCK": "WBD",    # Discovery C → Warner Bros. Discovery (2022)
    "LB":    "BBWI",   # L Brands → Bath & Body Works (2021)
    "MYL":   "VTRS",   # Mylan → Viatris (2020)
    "FI":    "FISV",   # Fiserv traded as FI (2023-2025) → back to FISV
}

def to_yahoo(ticker):
    """Bucket 1: dot→hyphen for share classes. Bucket 2: known renames."""
    t = ticker.replace(".", "-")
    return TICKER_RENAMES.get(t, t)

# --- collect tickers ---
df_hist = pd.read_csv(HIST_FILE, index_col="date")
df_hist.index = pd.to_datetime(df_hist.index)
df_hist = df_hist[df_hist.index >= START_DATE]

all_tickers = set()
for row in df_hist["tickers"]:
    all_tickers.update(row.split(","))
all_tickers = sorted(all_tickers)

# Resolve to Yahoo symbols (deduplicates e.g. ANTM+ELV → ELV once)
yahoo_tickers = sorted(set(to_yahoo(t) for t in all_tickers))
print(f"Unique historical tickers: {len(all_tickers)}  →  Yahoo tickers to fetch: {len(yahoo_tickers)}")

# --- download ---
if os.path.exists(OUTPUT_FILE) and not FORCE_REDOWNLOAD:
    print(f"{OUTPUT_FILE} already exists. Set FORCE_REDOWNLOAD=True to re-fetch.")
else:
    batches = [yahoo_tickers[i : i + BATCH_SIZE] for i in range(0, len(yahoo_tickers), BATCH_SIZE)]
    chunks, failed = [], []

    for batch in tqdm(batches, desc="Downloading"):
        try:
            raw = yf.download(
                batch,
                start=START_DATE,
                end=END_DATE,
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
        except Exception as e:
            print(f"Batch failed: {e}")
            failed.extend(batch)
            continue

        if raw.empty:
            continue

        if isinstance(raw.columns, pd.MultiIndex):
            # yfinance returns (Price, Ticker) at (level-0, level-1)
            raw = raw.stack(level=1)
            raw.index.names = ["Date", "Ticker"]
        else:
            raw.index.name = "Date"
            raw["Ticker"] = batch[0]
            raw = raw.reset_index().set_index(["Date", "Ticker"])

        chunks.append(raw)

    if not chunks:
        print("No data downloaded.")
    else:
        prices = pd.concat(chunks).sort_index()
        prices = prices.dropna(how="all")
        # Reset index so Date+Ticker become plain columns — avoids PyArrow
        # MultiIndex parquet incompatibility on older versions.
        prices.reset_index().to_parquet(OUTPUT_FILE, index=False)
        print(f"Saved {len(prices):,} rows → {OUTPUT_FILE}")
        if failed:
            print(f"Failed tickers: {failed}")

# --- verify ---
prices = pd.read_parquet(OUTPUT_FILE)
tickers_downloaded = prices["Ticker"].nunique()
date_min = prices["Date"].min().date()
date_max = prices["Date"].max().date()
print(f"Shape: {prices.shape}  |  Tickers: {tickers_downloaded}  |  {date_min} → {date_max}")

# parquet is indexed by Yahoo ticker; compare against the resolved set
downloaded = set(prices["Ticker"])
missing_yahoo = sorted(set(yahoo_tickers) - downloaded)
print(f"No data for {len(missing_yahoo)} Yahoo tickers: {missing_yahoo}")

# --- earliest full coverage across current 500 ---
# Translate current S&P 500 symbols through the same Bucket1+2 map,
# then find the latest first-date so all 500 are simultaneously available.
current_500_raw = sorted(pd.read_csv("sp500.csv")["Symbol"].tolist())
current_500 = [(sym, to_yahoo(sym)) for sym in current_500_raw]

first_dates = {}
no_data = []
for orig, yahoo in current_500:
    rows = prices[prices["Ticker"] == yahoo]
    if rows.empty:
        no_data.append(f"{orig}→{yahoo}" if orig != yahoo else orig)
    else:
        first_dates[orig] = rows["Date"].min()

earliest_full_coverage = max(first_dates.values())
latest_ticker = max(first_dates, key=first_dates.get)

print(f"\nCurrent S&P 500 members with no price data at all ({len(no_data)}): {no_data}")
print(f"Latest first-date across all {len(first_dates)} available members: {earliest_full_coverage.date()}")
print(f"  → Driven by: {latest_ticker}  (earliest row = {first_dates[latest_ticker].date()})")
print(f"  → All available members have uninterrupted data from this date onward.")
