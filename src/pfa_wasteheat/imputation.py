"""Build the cleaned values (new *_clean columns) for every row.

This replaces the old cases 1-16. Instead of 16 copied blocks, each row is handled by
the same rules depending on which fields were reported:

    annual (Q)  monthly (M)  ->  monthly energy                  annual energy
    yes         yes, fits        reported, best reading           reported
    yes         yes, no fit      best-reading shape, rescaled*    reported*
    no          yes              reported (reading A, else B)     sum of months
    yes         no               flat, spread by available hours  reported
    no          no, Pmax+hours   flat at max power                sum of months
    no          no, otherwise    -> no_energy_info (unusable)

    * with unmatched_strategy = trust_profile: reading-A monthly values are kept
      and the annual energy is replaced by their sum instead.

Finally, the monthly energies of every row are scaled to add up exactly to its clean
annual energy (for fitting rows this is a correction within the tolerance).

Max power and daily hours are kept when reported and derived otherwise.
Nothing is deleted, and every filled-in value is marked in *_source / was_imputed.
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

from . import columns as C
from .config import Config
from .energy import (
    INTERPRETATIONS, available_days, available_hours, flat_monthly_energy,
    full_month_hours, monthly_energy,
)

log = logging.getLogger(__name__)


def _pick_rows(stack: dict, choice: np.ndarray, n: int) -> np.ndarray:
    """For each row take the (12,) array of the interpretation named in `choice`."""
    out = np.full((n, 12), np.nan)
    for name, arr in stack.items():
        rows = choice == name
        out[rows] = arr[rows]
    return out


def build_clean_values(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    year = cfg.calendar_year
    strategy = cfg.consistency.unmatched_strategy

    has_q = df["has_annual"].to_numpy()
    has_m = df["has_monthly"].to_numpy()
    has_p = df["has_max_power"].to_numpy()
    has_d = df["has_daily_hours"].to_numpy()
    matched = df["interp_matched"].to_numpy()
    best = df["interp_best"].fillna("").to_numpy()

    q_raw = df[C.ANNUAL_KWH].to_numpy(dtype=float)
    p_raw = df[C.MAX_POWER_KW].to_numpy(dtype=float)
    d_raw = np.where(has_d, df[C.DAILY_HOURS].to_numpy(dtype=float), np.nan)
    weekend = df["weekend_available"].to_numpy()
    monthly_raw = df[C.POWER_COLS].to_numpy(dtype=float)

    stack = {i: monthly_energy(monthly_raw, i, d_raw, weekend, year) for i in INTERPRETATIONS}
    # Reading used when the profile cannot be checked: A if daily hours are known, else B.
    assumed = np.where(has_d, "A", "B")

    energy = np.full((n, 12), np.nan)
    annual = np.full(n, np.nan)
    monthly_src = np.full(n, "none", dtype=object)
    annual_src = np.full(n, "none", dtype=object)
    scale = np.full(n, np.nan)

    # 1) Q and M reported, a reading fits -> keep as reported
    r = has_q & has_m & matched
    energy[r] = _pick_rows(stack, best, n)[r]
    annual[r] = q_raw[r]
    monthly_src[r] = "reported:" + best[r].astype(object)
    annual_src[r] = "reported"

    # 2) Q and M reported, nothing fits
    r = has_q & has_m & ~matched
    if strategy == "trust_annual":
        shape = _pick_rows(stack, best, n)
        total = shape.sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            factor = q_raw / total
        ok = r & np.isfinite(factor) & (total > 0)
        energy[ok] = shape[ok] * factor[ok, None]
        scale[ok] = factor[ok]
        annual[ok] = q_raw[ok]
        monthly_src[ok] = "rescaled:" + best[ok].astype(object)
        annual_src[ok] = "reported"
    else:  # trust_profile
        shape = _pick_rows(stack, assumed, n)
        energy[r] = shape[r]
        annual[r] = shape[r].sum(axis=1)
        monthly_src[r] = "reported:" + assumed[r].astype(object)
        annual_src[r] = "from_monthly:" + assumed[r].astype(object)

    # 3) only M reported -> assume reading A (or B without daily hours)
    r = ~has_q & has_m
    shape = _pick_rows(stack, assumed, n)
    energy[r] = shape[r]
    annual[r] = shape[r].sum(axis=1)
    monthly_src[r] = "reported:" + assumed[r].astype(object) + "_assumed"
    annual_src[r] = "from_monthly:" + assumed[r].astype(object) + "_assumed"

    # 4) only Q reported -> flat profile, spread by available hours (or days)
    r = has_q & ~has_m
    weights = np.where(has_d[:, None], available_hours(d_raw, weekend, year), available_days(weekend, year))
    energy[r] = flat_monthly_energy(q_raw, weights)[r]
    annual[r] = q_raw[r]
    monthly_src[r] = "flat_from_annual"
    annual_src[r] = "reported"

    # 5) neither Q nor M, but max power and daily hours -> flat at max power (old case 9)
    r = ~has_q & ~has_m & has_p & has_d
    e5 = p_raw[:, None] * available_hours(d_raw, weekend, year)
    energy[r] = e5[r]
    annual[r] = e5[r].sum(axis=1)
    monthly_src[r] = "flat_from_max_power"
    annual_src[r] = "from_max_power"

    # Invariant: the 12 monthly energies always add up to the clean annual energy.
    # For rows that fit (case 1) this is a small adjustment within the tolerance
    # (the deviation is kept in interp_ratio); monthly shares are not affected.
    op_hours = np.where(has_d[:, None], available_hours(d_raw, weekend, year), full_month_hours(year)[None, :])

    def peak_kw(e):
        with np.errstate(divide="ignore", invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmax(np.where(op_hours > 0, e / op_hours, np.nan), axis=1)

    # Highest monthly power while available, from the monthly values BEFORE the final
    # adjustment below - used by the plausibility check against the reported max power.
    df["peak_monthly_kw"] = peak_kw(energy)

    total = energy.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        adjust = np.where(np.isfinite(annual) & (total > 0), annual / total, 1.0)
    energy = energy * adjust[:, None]

    df["no_energy_info"] = ~np.isfinite(annual)

    # --- Max power: reported, else highest monthly power while available ---
    derived_pmax = peak_kw(energy)
    pmax = np.where(has_p, p_raw, derived_pmax)
    pmax_src = np.where(has_p, "reported", np.where(np.isfinite(derived_pmax), "derived", "none"))

    # --- Daily hours: reported, else annual / reference power / available days ---
    # Reference power: mean monthly kW if the monthly values are powers, else max power.
    best_or_assumed = np.where(best != "", best, assumed)
    values_are_power = has_m & np.isin(best_or_assumed, ["A", "B", "W"])
    unit = np.where(best_or_assumed == "W", 1 / 1000, 1.0)
    with warnings.catch_warnings():  # all-NaN rows are expected (no monthly data)
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_monthly_kw = np.nanmean(np.where(monthly_raw > 0, monthly_raw, np.nan), axis=1) * unit
    ref_power = np.where(values_are_power, mean_monthly_kw, pmax)
    with np.errstate(divide="ignore", invalid="ignore"):
        derived_daily = annual / ref_power / available_days(weekend, year).sum(axis=1)
    daily = np.where(has_d, d_raw, derived_daily)
    daily_src = np.where(has_d, "reported", np.where(np.isfinite(derived_daily), "derived", "none"))

    df[C.ENERGY_COLS_CLEAN] = energy
    df[C.ANNUAL_KWH_CLEAN] = annual
    df[C.MAX_POWER_KW_CLEAN] = pmax
    df[C.DAILY_HOURS_CLEAN] = daily  # kept as a decimal number - no rounding
    df[C.ANNUAL_HOURS_CLEAN] = available_days(weekend, year).sum(axis=1) * daily
    with np.errstate(divide="ignore", invalid="ignore"):
        df[C.SHARE_COLS_CLEAN] = energy / energy.sum(axis=1, keepdims=True)
        df["full_load_hours"] = annual / pmax

    df["monthly_source"] = monthly_src
    df["annual_source"] = annual_src
    df["max_power_source"] = pmax_src
    df["daily_hours_source"] = daily_src
    df["was_rescaled"] = pd.Series(monthly_src, index=df.index).str.startswith("rescaled")
    df["scale_factor"] = scale

    imputed = pd.DataFrame({
        "monthly": ~pd.Series(monthly_src, index=df.index).str.startswith(("reported", "rescaled", "none")),
        "annual": ~pd.Series(annual_src, index=df.index).isin(["reported", "none"]),
        "max_power": pmax_src == "derived",
        "daily_hours": daily_src == "derived",
    }, index=df.index)
    df["imputed_fields"] = imputed.apply(lambda row: ",".join(row.index[row]), axis=1)
    df["was_imputed"] = imputed.any(axis=1)
    df["is_flat_profile_clean"] = pd.Series(monthly_src, index=df.index).str.startswith("flat") | df["is_flat_profile_raw"]

    log.info("Clean values: %d rescaled, %d with imputed fields, %d without energy information",
             int(df["was_rescaled"].sum()), int(df["was_imputed"].sum()), int(df["no_energy_info"].sum()))
    return df
