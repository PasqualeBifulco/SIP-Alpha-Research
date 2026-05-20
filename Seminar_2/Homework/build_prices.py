"""
Builds sp500_prices.parquet using current S&P 500 constituents.
Uses yf.download() in batches of 50 tickers for speed.
"""
import pandas as pd
import yfinance as yf

TICKER_CSV = "sp500/sp500_ticker_start_end.csv"
START = "2001-01-01"
OUT = "sp500_prices.parquet"
BATCH = 50

tdf = pd.read_csv(TICKER_CSV)
# current constituents = no end_date (still in index)
current = tdf[tdf["end_date"].isna()]["ticker"].unique().tolist()
print(f"Current S&P 500 tickers: {len(current)}")

fields = ["Open", "High", "Low", "Close", "Volume"]
frames = []

for i in range(0, len(current), BATCH):
    batch = current[i : i + BATCH]
    print(f"  Batch {i//BATCH + 1}/{-(-len(current)//BATCH)}  ({batch[0]}...{batch[-1]})")
    try:
        raw = yf.download(batch, start=START, auto_adjust=True, progress=False, threads=True)
        if raw.empty:
            print("    empty, skipping")
            continue

        if isinstance(raw.columns, pd.MultiIndex):
            # MultiIndex: (field, ticker) — select OHLCV fields, stack tickers to rows
            available = [f for f in fields if f in raw.columns.get_level_values(0)]
            sub = raw[available]
            df = sub.stack(level=1).reset_index()
            df.columns.name = None
            # after stack the ticker level becomes a column; rename it
            cols = list(df.columns)
            # first col is Date-like, second is the stacked ticker level
            date_col  = cols[0]
            ticker_col = cols[1]
            df = df.rename(columns={date_col: "Date", ticker_col: "Ticker"})
        else:
            # single ticker
            df = raw[fields].reset_index()
            df.columns.name = None
            df["Ticker"] = batch[0]
            df = df.rename(columns={df.columns[0]: "Date"})

        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
        keep = [c for c in ["Date", "Ticker"] + fields if c in df.columns]
        frames.append(df[keep])
        print(f"    got {len(df):,} rows")
    except Exception as e:
        print(f"    WARN: {e}")

print("Concatenating...")
prices = pd.concat(frames, ignore_index=True)
prices = prices.dropna(subset=["Close"])
prices = prices.sort_values(["Date", "Ticker"]).reset_index(drop=True)
prices.to_parquet(OUT, index=False)
print(f"\nDone! {len(prices):,} rows saved to {OUT}")
print(f"Tickers: {prices['Ticker'].nunique()}  |  {prices['Date'].min().date()} -> {prices['Date'].max().date()}")
