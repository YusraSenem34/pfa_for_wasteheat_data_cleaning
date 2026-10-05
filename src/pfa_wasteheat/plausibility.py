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
    # Only where daily hours were reported: derived daily hours come from max power, which
    # would make the comparison circular.
    pmax = df[C.MAX_POWER_KW_CLEAN]
    reported_pmax = df["max_power_source"].eq("reported") & df["daily_hours_source"].eq("reported")
    df["pmax_below_monthly"] = reported_pmax & (df["peak_monthly_kw"] > pmax * (1 + tol))
    # Far above: a peak can exceed the monthly level, but not by a factor of 100+ (unit error).
    df["pmax_far_above_monthly"] = (reported_pmax & df["has_monthly"]
                                    & (pmax > pl.pmax_far_above_factor * df["peak_monthly_kw"]))

    flh = df["full_load_hours"]
    df["flh_impossible"] = flh > hours_in_year(year) * (1 + tol)
    df["flh_exceeds_availability"] = flh > df[C.ANNUAL_HOURS_CLEAN] * (1 + tol)
    df["daily_hours_impossible"] = df[C.DAILY_HOURS_CLEAN] > 24 * (1 + tol)

    # --- Reporting style: rough estimates (reported values only) ---
    est_tol = pl.estimate_tolerance
    q_raw, p_raw = df[C.ANNUAL_KWH], df[C.MAX_POWER_KW]
    both = df["has_annual"] & df["has_max_power"] & df["has_daily_hours"]
    with np.errstate(divide="ignore", invalid="ignore"):
        df["annual_equals_pmax_x_hours"] = both & ((q_raw / (p_raw * df[C.ANNUAL_HOURS_CLEAN]) - 1).abs() < est_tol)
        df["profile_flat_at_pmax"] = (df["is_flat_profile_raw"] & df["has_max_power"]
                                      & ((df[C.POWER_COLS[0]] / p_raw - 1).abs() < est_tol))

    # --- Duplicates ---
    raw_cols = [C.COMPANY, C.SITE, C.SOURCE_NAME, C.ANNUAL_KWH, C.MAX_POWER_KW, C.TEMP_C,
                C.DAILY_HOURS, C.WEEKEND] + C.POWER_COLS
    df["is_duplicate_exact"] = df.duplicated(subset=raw_cols, keep="first")
    key = [C.SITE_ID, C.SOURCE_NAME]
    dup_any = df.duplicated(subset=key, keep=False)
    df["is_duplicate_name"] = dup_any
    df["duplicate_group"] = np.where(dup_any, df.groupby(key, dropna=False).ngroup(), -1)
    value_cols = [C.SITE_ID, C.ANNUAL_KWH, C.MAX_POWER_KW, C.TEMP_C, C.DAILY_HOURS, C.WEEKEND] + C.POWER_COLS
    exact_any = df.duplicated(subset=raw_cols, keep=False)
    df["is_duplicate_values"] = df.duplicated(subset=value_cols, keep=False) & ~exact_any

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

    flag_cols = ["temp_implausible", "temp_range_mismatch", "pmax_below_monthly", "pmax_far_above_monthly",
                 "flh_impossible", "flh_exceeds_availability", "daily_hours_impossible",
                 "annual_equals_pmax_x_hours", "profile_flat_at_pmax", "is_duplicate_exact",
                 "is_duplicate_name", "is_duplicate_values", "below_plant_threshold", "below_site_threshold"]
    log.info("Plausibility flags: %s", {c: int(df[c].sum()) for c in flag_cols})
    return df


UNCLEAR_MEDIUM = {"Unknown", "Unclear", "Invalid", "Error"}


def add_medium_flags(df: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Merge LLM medium labels (by row_id) and check them against the temperature.

    Labels are only used where the source name still matches, so labels produced for
    another release of the register are not attached to the wrong rows.
    """
    df = df.copy()
    missing = {C.ROW_ID, C.SOURCE_NAME, "LLM_Category"} - set(labels.columns)
    if missing:
        log.warning("LLM label file lacks %s - medium flags skipped. Re-create it with "
                    "python -m pfa_wasteheat.enrich.medium_llm", sorted(missing))
        return df
    lab = labels[[C.ROW_ID, C.SOURCE_NAME, "LLM_Category"]].rename(columns={C.SOURCE_NAME: "_label_name"})
    df = df.drop(columns=["LLM_Category"], errors="ignore").merge(lab, on=C.ROW_ID, how="left")
    mismatch = df["_label_name"].notna() & (df["_label_name"] != df[C.SOURCE_NAME])
    if mismatch.any():
        log.warning("Ignoring %d LLM labels whose source name does not match (other release?)", mismatch.sum())
        df.loc[mismatch, "LLM_Category"] = np.nan
    df = df.drop(columns="_label_name")

    df["medium_unclear"] = df["LLM_Category"].isna() | df["LLM_Category"].isin(UNCLEAR_MEDIUM)
    df["steam_below_100c"] = df["LLM_Category"].eq("Steam") & (df[C.TEMP_C] < 100)
    log.info("Medium flags: medium_unclear=%d, steam_below_100c=%d",
             int(df["medium_unclear"].sum()), int(df["steam_below_100c"].sum()))
    return df
