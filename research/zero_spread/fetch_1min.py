"""Twelve Data 1-minute OHLC loader with on-disk CSV cache.

Keeps the same API-key sourcing pattern as `research/zscore_notify.py`. The
free Twelve Data tier limits 1-min history to ~7 days per call; we page
backwards in chunks and merge into a single sorted CSV per pair.

Output: research/zero_spread/data/<PAIR_NO_SLASH>_1min.csv
Columns: datetime (UTC ISO), open, high, low, close
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests


API = "https://api.twelvedata.com/time_series"
CHUNK_BARS = 5000   # max per request on free tier
PAGE_SLEEP = 8      # seconds between requests (8 calls/min free tier limit)


def _load_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close"])
    df = pd.read_csv(path, parse_dates=["datetime"])
    if df["datetime"].dt.tz is None:
        df["datetime"] = df["datetime"].dt.tz_localize("UTC")
    return df


def _request_page(pair: str, end_dt: datetime, api_key: str) -> pd.DataFrame:
    params = {
        "symbol": pair,
        "interval": "1min",
        "outputsize": CHUNK_BARS,
        "apikey": api_key,
        "end_date": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "JSON",
        "timezone": "UTC",
    }
    for attempt in range(4):
        try:
            r = requests.get(API, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            wait = 2 ** (attempt + 1)
            print(f"  retry in {wait}s ({e})", file=sys.stderr)
            time.sleep(wait)
            continue
        if data.get("status") == "error":
            print(f"  api error: {data.get('message')}", file=sys.stderr)
            return pd.DataFrame()
        rows = data.get("values", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        for c in ("open", "high", "low", "close"):
            df[c] = df[c].astype(float)
        return df[["datetime", "open", "high", "low", "close"]].sort_values("datetime")
    return pd.DataFrame()


def fetch_pair(pair: str, start: datetime, end: datetime, api_key: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (pair.replace("/", "") + "_1min.csv")
    existing = _load_existing(out_path)
    earliest_have = existing["datetime"].min() if not existing.empty else None

    cursor = end
    pages: list[pd.DataFrame] = []
    while cursor > start:
        if earliest_have is not None and cursor <= earliest_have:
            # We've already cached everything older than this point.
            break
        print(f"[{pair}] fetching ending {cursor:%Y-%m-%d %H:%M}")
        page = _request_page(pair, cursor, api_key)
        if page.empty:
            break
        pages.append(page)
        first_ts = page["datetime"].min().to_pydatetime().replace(tzinfo=timezone.utc)
        if first_ts >= cursor:
            break  # not making progress
        cursor = first_ts - timedelta(minutes=1)
        time.sleep(PAGE_SLEEP)

    if pages or not existing.empty:
        merged = pd.concat([existing] + pages, ignore_index=True)
        merged = merged.drop_duplicates(subset=["datetime"]).sort_values("datetime")
        merged = merged[(merged["datetime"] >= pd.Timestamp(start, tz="UTC")) &
                        (merged["datetime"] <= pd.Timestamp(end, tz="UTC"))]
        merged.to_csv(out_path, index=False)
        print(f"[{pair}] wrote {len(merged):,} bars to {out_path}")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--pair", action="append",
                   help="Pair(s) to fetch. Default: all enabled in config.")
    p.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD UTC")
    p.add_argument("--to", required=True, help="YYYY-MM-DD UTC")
    p.add_argument("--out-dir", type=Path,
                   default=Path(__file__).parent / "data")
    args = p.parse_args()

    cfg = json.loads(args.config.read_text())
    api_key = cfg.get("twelve_data_api_key")
    if not api_key:
        print("ERROR: twelve_data_api_key missing from config", file=sys.stderr)
        sys.exit(1)

    pairs = args.pair or [p for p, c in cfg["pairs"].items() if c.get("enabled", True)]
    start = datetime.fromisoformat(args.frm).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.to).replace(tzinfo=timezone.utc)
    for pair in pairs:
        fetch_pair(pair, start, end, api_key, args.out_dir)


if __name__ == "__main__":
    main()
