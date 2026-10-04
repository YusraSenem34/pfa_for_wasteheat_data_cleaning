"""Calendar and energy calculations. Pure functions on arrays - no state, no I/O.

Central idea: every reading ("interpretation") of the 12 monthly columns is converted
to monthly ENERGY in kWh. Monthly energy is unambiguous, so all later steps
(consistency check, imputation, profile shapes) work on the same quantity.
"""

from __future__ import annotations

import calendar
from datetime import date
from functools import lru_cache
from typing import Dict

import numpy as np
from workalendar.europe import Germany

# Readings of the monthly columns that are tested against the reported annual energy.
INTERPRETATIONS: Dict[str, str] = {
    "A": "kW while the source is available (daily hours x available days)",
    "B": "kW averaged over the whole month (24 h x all days)",
    "C": "monthly energy in kWh, not power",
    "W": "W instead of kW, while available (A / 1000)",
    "Wh": "monthly energy in Wh, not kWh (C / 1000)",
}
NEEDS_DAILY_HOURS = {"A", "W"}


@lru_cache(maxsize=None)
def month_days(year: int) -> np.ndarray:
    """Number of calendar days in each month."""
    return np.array([calendar.monthrange(year, m)[1] for m in range(1, 13)], dtype=float)


@lru_cache(maxsize=None)
def month_working_days(year: int) -> np.ndarray:
    """Mon-Fri minus nationwide German public holidays, per month."""
    cal = Germany()
    return np.array(
        [sum(cal.is_working_day(date(year, m, d)) for d in range(1, calendar.monthrange(year, m)[1] + 1))
         for m in range(1, 13)],
        dtype=float,
    )


def available_days(weekend_available: np.ndarray, year: int) -> np.ndarray:
    """(n, 12) days per month on which the source is available."""
    w = np.asarray(weekend_available, dtype=bool)[:, None]
    return np.where(w, month_days(year)[None, :], month_working_days(year)[None, :])


def available_hours(daily_hours: np.ndarray, weekend_available: np.ndarray, year: int) -> np.ndarray:
    """(n, 12) hours per month in which the source is available (NaN if daily hours unknown)."""
    return available_days(weekend_available, year) * np.asarray(daily_hours, dtype=float)[:, None]


def full_month_hours(year: int) -> np.ndarray:
    return 24.0 * month_days(year)


def hours_in_year(year: int) -> float:
    return float(full_month_hours(year).sum())


def monthly_energy(
    monthly_values: np.ndarray,
    interpretation: str,
    daily_hours: np.ndarray,
    weekend_available: np.ndarray,
    year: int,
) -> np.ndarray:
    """Convert the 12 reported monthly values to monthly energy (kWh) under one reading.

    Returns an (n, 12) array; rows where the reading cannot be computed
    (A/W without daily hours) are NaN.
    """
    p = np.asarray(monthly_values, dtype=float)
    if interpretation == "A":
        return p * available_hours(daily_hours, weekend_available, year)
    if interpretation == "B":
        return p * full_month_hours(year)[None, :]
    if interpretation == "C":
        return p.copy()
    if interpretation == "W":
        return p / 1000.0 * available_hours(daily_hours, weekend_available, year)
    if interpretation == "Wh":
        return p / 1000.0
    raise ValueError(f"Unknown interpretation {interpretation!r}")


def flat_monthly_energy(annual_kwh: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Spread an annual amount over the months proportionally to `weights` (n, 12)."""
    w = np.asarray(weights, dtype=float)
    total = w.sum(axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.asarray(annual_kwh, dtype=float)[:, None] * w / total
