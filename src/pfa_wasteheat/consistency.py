"""Which fields were reported, and do annual energy and monthly profile agree?

For every row where both the annual energy and the monthly profile are reported,
ALL readings of the monthly columns (see energy.INTERPRETATIONS) are tested.
The closest one wins - not the first one that happens to fit.

Readings that involve the calendar (A, B, W, MW) use `tolerance`; pure energy
readings (C, Wh, MWh) use the tighter `tolerance_exact`, because a unit error
there produces an exact factor.

Before the readings are tested, the annual energy itself is checked for the reverse
unit error: annual energy given in MWh instead of kWh (check_annual_unit). If so, the
readings are tested against annual x 1000.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import columns as C
from .config import Config
from .energy import (
    EXACT_READINGS, INTERPRETATIONS, NEEDS_DAILY_HOURS, available_hours, full_month_hours,
    hours_in_year, monthly_energy,
)

log = logging.getLogger(__name__)

# Readings that keep the reported unit (kW). Matches here = "consistent as reported".
AS_REPORTED = {"A", "B"}


def add_presence_flags(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """has_* = the field holds a real value (above the placeholder limits in config)."""
    p = cfg.presence
    df = df.copy()
    df["has_annual"] = df[C.ANNUAL_KWH] > p.annual_kwh_min
    df["has_max_power"] = df[C.MAX_POWER_KW] > p.max_power_kw_min
    df["has_monthly"] = (df[C.POWER_COLS] > p.monthly_kw_min).any(axis=1)
    df["has_daily_hours"] = df[C.DAILY_HOURS] > p.daily_hours_min
    df["has_temperature"] = df[C.TEMP_C].notna()

    monthly = df[C.POWER_COLS]
    df["is_flat_profile_raw"] = df["has_monthly"] & monthly.nunique(axis=1).eq(1)
    df["n_active_months"] = (monthly > 0).sum(axis=1).where(df["has_monthly"])
    df["has_inactive_months"] = df["has_monthly"] & (df["n_active_months"] < 12)
    return df


def check_annual_unit(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Flag rows whose annual energy was evidently given in MWh instead of kWh.

    Full-load hours as reported (annual kWh / max power kW) below hours_in_year / 1000
    mean the source would deliver its whole year's energy in a few hours - impossible.
    x1000 turns them into normal full-load hours. Required as well, so that "max power
    and monthly values in W" is not mistaken for this case:
      - reported annual energy small (< annual_mwh_max_reported_kwh, default 200 MWh)
      - max power believable in kW (<= annual_mwh_max_power_kw, default 100 MW)
      - after x1000 at least annual_mwh_min_flh_after full-load hours (default 50 h)
    """
    c = cfg.consistency
    df = df.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        flh_reported = df[C.ANNUAL_KWH] / df[C.MAX_POWER_KW]
    limit = hours_in_year(cfg.calendar_year) / 1000 * (1 + cfg.plausibility.limit_tolerance)
    df["annual_in_mwh"] = (
        df["has_annual"] & df["has_max_power"]
        & (flh_reported <= limit)
        & (flh_reported * 1000 >= c.annual_mwh_min_flh_after)
        & (df[C.ANNUAL_KWH] < c.annual_mwh_max_reported_kwh)
        & (df[C.MAX_POWER_KW] <= c.annual_mwh_max_power_kw)
    ).fillna(False).astype(bool)
    log.info("Annual energy given in MWh (x1000): %d rows", int(df["annual_in_mwh"].sum()))
    return df


def check_consistency(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    df = df.copy()
    tol = cfg.consistency.tolerance
    tol_exact = cfg.consistency.tolerance_exact
    year = cfg.calendar_year
    interps = [i for i in cfg.consistency.interpretations if i in INTERPRETATIONS]

    testable = (df["has_annual"] & df["has_monthly"]).to_numpy()
    reported = df[C.ANNUAL_KWH].to_numpy(dtype=float)
    if "annual_in_mwh" in df:
        reported = np.where(df["annual_in_mwh"].to_numpy(), reported * 1000.0, reported)
    daily = df[C.DAILY_HOURS].where(df["has_daily_hours"]).to_numpy(dtype=float)
    weekend = df["weekend_available"].to_numpy()
    monthly = df[C.POWER_COLS].to_numpy(dtype=float)

    ratios = {}
    for i in interps:
        calc = monthly_energy(monthly, i, daily, weekend, year).sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(testable & (calc > 0), reported / calc, np.nan)
        ratios[i] = r
        df[f"ratio_{i}"] = r  # reported / recalculated; 1.0 = perfect agreement

    ratio_df = pd.DataFrame(ratios, index=df.index)
    log_dev = np.abs(np.log(ratio_df))
    tolerances = pd.Series({i: tol_exact if i in EXACT_READINGS else tol for i in interps})
    matched = (ratio_df - 1).abs() <= tolerances

    # A and B are the same reading for sources available 24 h on all days.
    a_equals_b = np.isclose(
        available_hours(daily, weekend, year), full_month_hours(year)[None, :]
    ).all(axis=1)
    distinct = matched.copy()
    if {"A", "B"} <= set(interps):
        distinct.loc[a_equals_b & matched["A"].to_numpy(), "B"] = False

    # Closest reading wins - but a reading that keeps the reported unit is preferred
    # whenever it fits, so a unit "fix" is only chosen if it is actually needed.
    as_rep_cols = [i for i in interps if i in AS_REPORTED]
    as_rep_fits = matched[as_rep_cols].any(axis=1) if as_rep_cols else pd.Series(False, index=df.index)
    dev_for_choice = log_dev.copy()
    other_cols = [i for i in interps if i not in AS_REPORTED]
    dev_for_choice.loc[as_rep_fits, other_cols] = np.nan
    dev_arr = dev_for_choice.to_numpy(dtype=float)
    any_valid = ~np.isnan(dev_arr).all(axis=1)
    best_pos = np.argmin(np.where(np.isnan(dev_arr), np.inf, dev_arr), axis=1)
    best = pd.Series(np.array(interps, dtype=object)[best_pos], index=df.index).where(any_valid)
    best_ratio = pd.Series(
        ratio_df.to_numpy(dtype=float)[np.arange(len(df)), best_pos], index=df.index
    ).where(any_valid)

    df["interp_matched"] = matched.any(axis=1)
    df["interp_matches"] = matched.apply(lambda r: ",".join(r.index[r]), axis=1)
    df["n_interp_matches"] = distinct.sum(axis=1)

    df["interp_best"] = best
    df["interp_ratio"] = best_ratio
    # Ambiguous: several readings fit - or W/Wh fits but there is no max power, so
    # "annual energy in MWh" (check_annual_unit) could not be tested as the alternative.
    no_pmax_check = best.isin(["W", "Wh"]) & ~df["has_max_power"] & df["interp_matched"]
    df["interp_ambiguous"] = (df["n_interp_matches"] > 1) | no_pmax_check

    annual_fixed = df["annual_in_mwh"] if "annual_in_mwh" in df else pd.Series(False, index=df.index)
    status = np.select(
        [~testable,
         df["interp_matched"] & df["interp_best"].isin(AS_REPORTED) & ~annual_fixed,
         df["interp_matched"]],
        ["not_testable", "consistent_as_reported", "consistent_after_unit_fix"],
        default="inconsistent",
    )
    df["consistency_status"] = status

    counts = df["consistency_status"].value_counts().to_dict()
    log.info("Consistency (tolerance %.0f%%, exact readings %.0f%%): %s", tol * 100, tol_exact * 100, counts)
    return df


def interpretation_needs_daily_hours(interp: str) -> bool:
    return interp in NEEDS_DAILY_HOURS
