"""
Scrape all SEC Form 4 (insider trading) filings for every ticker in
tickers_with_data.csv, from 2005 to today, using edgartools.

Output: one tidy CSV per ticker (form4_data/form4_<TICKER>.csv) plus a
combined parquet (form4_data/form4_all.parquet). One row per transaction.

Install:  pip install edgartools pandas pyarrow
"""

import time
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from edgar import Company, set_identity

# ----------------------------- CONFIG --------------------------------------
set_identity("gsundaram1999@gmail.com")

TICKERS_FILE  = "tickers_with_data.csv"
START_DATE    = "2005-01-01"
END_DATE      = date.today().isoformat()

OUTDIR        = Path("form4_data")
SKIP_IF_DONE  = True   # skip tickers whose CSV already exists (resumable)
MAX_WORKERS   = 4      # SEC allows ~10 req/s; 4 threads is safe
SLEEP_BETWEEN_FILINGS = 0.0
# ---------------------------------------------------------------------------

OUTDIR.mkdir(exist_ok=True)


def scrape_ticker(ticker: str) -> pd.DataFrame:
    """Pull every Form 4 / 4-A for one ticker and return a per-transaction df."""
    out_path = OUTDIR / f"form4_{ticker}.csv"
    if SKIP_IF_DONE and out_path.exists():
        print(f"[{ticker}] already done -> {out_path}")
        return pd.read_csv(out_path)

    company = Company(ticker)
    filings = company.get_filings(
        form="4",
        filing_date=f"{START_DATE}:{END_DATE}",
    )
    n = len(filings)
    print(f"[{ticker}] {n} Form 4 filings found")

    rows = []
    for i, filing in enumerate(filings):
        try:
            obj = filing.obj()
            df = obj.to_dataframe(detailed=True, include_metadata=True)
        except Exception as e:
            print(f"  [{ticker}] skip {filing.accession_no}: {e}")
            continue

        if df is None or df.empty:
            continue

        df = df.copy()
        df["filing_form"]         = filing.form
        df["is_amendment"]        = str(filing.form).endswith("/A")
        df["filing_date"]         = filing.filing_date
        df["acceptance_datetime"] = filing.acceptance_datetime
        df["accession_no"]        = filing.accession_no
        df["query_ticker"]        = ticker
        rows.append(df)

        if SLEEP_BETWEEN_FILINGS:
            time.sleep(SLEEP_BETWEEN_FILINGS)
        if (i + 1) % 100 == 0:
            print(f"  [{ticker}] ...{i + 1}/{n}")

    if not rows:
        print(f"[{ticker}] no transactions parsed")
        return pd.DataFrame()

    result = pd.concat(rows, ignore_index=True)
    result.to_csv(out_path, index=False)
    print(f"[{ticker}] saved {len(result)} rows -> {out_path}")
    return result


def main() -> None:
    tickers = pd.read_csv(TICKERS_FILE)["Ticker"].tolist()
    print(f"Loaded {len(tickers)} tickers from {TICKERS_FILE}")

    all_frames = []
    failed = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scrape_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    all_frames.append(df)
            except Exception as e:
                print(f"[{ticker}] FAILED: {e}")
                failed.append(ticker)

    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        combined_path = OUTDIR / "form4_all.parquet"
        combined.to_parquet(combined_path, index=False)
        print(f"\nTOTAL: {len(combined)} rows across {len(all_frames)} tickers")
        print(f"Saved -> {combined_path}")

    if failed:
        print(f"\nFailed ({len(failed)}): {failed}")


if __name__ == "__main__":
    main()