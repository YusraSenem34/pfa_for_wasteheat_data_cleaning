"""Physical plausibility, duplicate and BfEE-threshold flags. Nothing is removed here."""

from __future__ import annotations

import logging
import re

import numpy as np
import pandas as pd

from . import columns as C
from .config import Config
from .energy import hours_in_year

log = logging.getLogger(__name__)


def parse_temperature_range(label: str | float) -> tuple[float, float]:
    """'25 - 60 °c' -> (25, 60); '>=110 °c' -> (110, inf); '<25 °c' -> (-inf, 25)."""
    if not isinstance(label, str):
        return (np.nan, np.nan)
    nums = [float(x) for x in re.findall(r"\d+(?:[.,]\d+)?", label.replace(",", "."))]
    if label.strip().startswith(">") and nums:
        return (nums[0], np.inf)
    if label.strip().startswith("<") and nums:
        return (-np.inf, nums[0])
    if len(nums) >= 2:
        return (nums[0], nums[1])
    return (np.nan, np.nan)


def add_plausibility_flags(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    df = df.copy()
    pl = cfg.plausibility
    tol = pl.limit_tolerance
    year = cfg.calendar_year

    # --- Temperature ---
    t = df[C.TEMP_C]
    df["temp_implausible"] = df["has_temperature"] & ((t < pl.temperature_min_c) | (t > pl.temperature_max_c))
    bounds = df[C.TEMP_RANGE].map(parse_temperature_range)
    lo = bounds.map(lambda b: b[0])
    hi = bounds.map(lambda b: b[1])
    # 1 K slack for rounding at the category borders
    df["temp_range_mismatch"] = df["has_temperature"] & lo.notna() & ((t < lo - 1) | (t > hi + 1))

    # --- Power and hours ---
    # Reported max power lower than the highest monthly power -> the two fields contradict.
    pmax = df[C.MAX_POWER_KW_CLEAN]
    reported_pmax = df["max_power_source"].eq("reported")
    df["pmax_below_monthly"] = reported_pmax & (df["peak_monthly_kw"] > pmax * (1 + tol))

    flh = df["full_load_hours"]
    df["flh_impossible"] = flh > hours_in_year(year) * (1 + tol)
    df["flh_exceeds_availability"] = flh > df[C.ANNUAL_HOURS_CLEAN] * (1 + tol)
    df["daily_hours_impossible"] = df[C.DAILY_HOURS_CLEAN] > 24 * (1 + tol)

    # --- Duplicates ---
    raw_cols = [C.COMPANY, C.SITE, C.SOURCE_NAME, C.ANNUAL_KWH, C.MAX_POWER_KW, C.TEMP_C,
                C.DAILY_HOURS, C.WEEKEND] + C.POWER_COLS
    df["is_duplicate_exact"] = df.duplicated(subset=raw_cols, keep="first")
    key = [C.SITE_ID, C.SOURCE_NAME]
    dup_any = df.duplicated(subset=key, keep=False)
    df["is_duplicate_name"] = dup_any
    df["duplicate_group"] = np.where(dup_any, df.groupby(key, dropna=False).ngroup(), -1)

    # --- BfEE de-minimis thresholds (flag only) ---
    th = cfg.bfee_thresholds
    q = df[C.ANNUAL_KWH_CLEAN]
    df["below_200mwh"] = q < th.plant_min_annual_kwh
    df["below_1500h"] = df[C.ANNUAL_HOURS_CLEAN] < th.plant_min_hours
    df["below_25c"] = t < th.plant_min_temperature_c
    df["below_plant_threshold"] = df["below_200mwh"] | df["below_1500h"] | df["below_25c"]

    # Site rule: sum of the sources at a site that pass the plant rule.
    site_total = q.where(~df["below_plant_threshold"], 0).groupby(df[C.SITE_ID]).transform("sum")
    df["site_total_kwh"] = site_total
    df["below_site_threshold"] = site_total < th.site_min_annual_kwh
    df["below_bfee_threshold"] = df["below_plant_threshold"] | df["below_site_threshold"]

    # --- Medium vs temperature (only once the LLM medium column exists) ---
    if "LLM_Category" in df.columns:
        df["steam_below_100c"] = df["LLM_Category"].eq("Steam") & (t < 100)

    flag_cols = ["temp_implausible", "temp_range_mismatch", "pmax_below_monthly", "flh_impossible",
                 "flh_exceeds_availability", "daily_hours_impossible", "is_duplicate_exact",
                 "is_duplicate_name", "below_plant_threshold", "below_site_threshold"]
    log.info("Plausibility flags: %s", {c: int(df[c].sum()) for c in flag_cols})
    return df
