"""Geocode site addresses with Nominatim (OpenStreetMap).

Improvements over the old geocode.py:
- every distinct address is geocoded once (about 5,700 sites instead of 22,000 rows)
- results are cached in data/processed/geocode_cache.parquet, so an interrupted run resumes
- coordinates already produced by the old pipeline can be re-used (import_legacy_coordinates)

    python -m pfa_wasteheat.enrich.geocode --legacy data/data_with_coordinates_all_latest.xlsx
    python -m pfa_wasteheat.enrich.geocode            # geocode whatever is still missing
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from .. import columns as C
from ..config import load_config

log = logging.getLogger(__name__)

CACHE_NAME = "geocode_cache.parquet"


def full_address(df: pd.DataFrame) -> pd.Series:
    return (df[C.STREET].fillna("") + ", " + df[C.POSTAL_CODE].fillna("") + " "
            + df[C.CITY].fillna("") + ", Germany").str.strip()


def import_legacy_coordinates(df: pd.DataFrame, legacy_file: str | Path) -> pd.DataFrame:
    """Take lat/long from the old geocoded Excel file, matched by the original Excel row."""
    old = pd.read_excel(legacy_file, usecols=[C.EXCEL_ROW, "lat", "long"])
    old = old.drop_duplicates(C.EXCEL_ROW)
    out = df[[C.EXCEL_ROW]].merge(old, on=C.EXCEL_ROW, how="left")
    out["address"] = full_address(df).to_numpy()
    cache = out.dropna(subset=["lat"]).groupby("address", as_index=False)[["lat", "long"]].first()
    log.info("Imported coordinates for %d addresses from %s", len(cache), legacy_file)
    return cache


def geocode_missing(addresses: pd.Series, cache: pd.DataFrame) -> pd.DataFrame:
    """Geocode addresses that are not in the cache yet. Returns the updated cache."""
    from geopy.extra.rate_limiter import RateLimiter
    from geopy.geocoders import Nominatim

    todo = sorted(set(addresses.dropna()) - set(cache["address"]))
    log.info("%d addresses to geocode (1 request per second)", len(todo))
    geocode = RateLimiter(Nominatim(user_agent="pfa_wasteheat_thesis", timeout=10).geocode,
                          min_delay_seconds=1, error_wait_seconds=10)
    new = []
    for k, addr in enumerate(todo, 1):
        try:
            loc = geocode(addr)
        except Exception as exc:
            log.warning("%s: %s", addr, exc)
            loc = None
        new.append({"address": addr, "lat": loc.latitude if loc else None,
                    "long": loc.longitude if loc else None})
        if k % 100 == 0:
            log.info("%d / %d", k, len(todo))
    return pd.concat([cache, pd.DataFrame(new)], ignore_index=True)


def add_coordinates(df: pd.DataFrame, cache: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["full_address"] = full_address(df)
    return df.merge(cache.rename(columns={"address": "full_address"}), on="full_address", how="left")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Geocode site addresses")
    parser.add_argument("--legacy", default=None, help="old Excel file with lat/long to re-use")
    parser.add_argument("--no-online", action="store_true", help="only use cache/legacy, no requests")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    cfg = load_config()
    out_dir = Path(cfg.paths.output_dir)
    df = pd.read_parquet(out_dir / "pfa_cleaned.parquet")
    cache_path = out_dir / CACHE_NAME
    cache = pd.read_parquet(cache_path) if cache_path.exists() else pd.DataFrame(columns=["address", "lat", "long"])

    if args.legacy:
        legacy = import_legacy_coordinates(df, args.legacy)
        cache = pd.concat([cache, legacy]).drop_duplicates("address", keep="first")
    if not args.no_online:
        cache = geocode_missing(full_address(df), cache)
    cache.to_parquet(cache_path, index=False)

    geo = add_coordinates(df, cache)
    geo.to_parquet(out_dir / "pfa_cleaned_geo.parquet", index=False)
    log.info("Coordinates found for %d of %d rows", geo["lat"].notna().sum(), len(geo))


if __name__ == "__main__":
    main()
