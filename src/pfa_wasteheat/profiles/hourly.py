"""Hourly (8760 h) waste heat profile from one cleaned row.

Replaces the old waste_heat_generator.py. Differences:
- uses the cleaned monthly ENERGY, so the hourly profile always adds up to the
  cleaned annual energy (energy-conserving), whatever reading the reporter used
- uses the real average temperature (old code used the upper bound of Temperature_Range
  and mixed up the temperature with AVG_Thermal_Power)
- leap years get 8784 hours

Assumed operating pattern (the register gives no time of day): a block of
round(daily hours) per available day, starting at 08:00, or at 00:00 for >16 h/day.
Without weekend availability, weekends and nationwide public holidays are off.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import numpy as np
import pandas as pd
from workalendar.europe import Germany

from .. import columns as C
from .models import EnergyProfile, WasteHeatProfile


def operating_window(daily_hours: float) -> tuple[int, int]:
    hours = int(min(24, max(1, round(float(daily_hours)))))
    start = 0 if hours > 16 else 8
    return start, min(24, start + hours)


def hourly_profile(row: pd.Series, year: int) -> pd.Series:
    """kW for every hour of `year`. Sum over the year == annual_kwh_clean."""
    if not np.isfinite(row[C.ANNUAL_KWH_CLEAN]):
        raise ValueError("Row has no energy information (quality tier D: no_energy_info)")

    idx = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", inclusive="left")
    start, end = operating_window(row[C.DAILY_HOURS_CLEAN])
    in_window = (idx.hour >= start) & (idx.hour < end)

    if bool(row["weekend_available"]):
        active = in_window
    else:
        holidays = {d for d, _ in Germany().holidays(year)}
        workday = (idx.weekday < 5) & ~pd.Index(idx.date).isin(holidays)
        active = in_window & workday

    energy = row[C.ENERGY_COLS_CLEAN].to_numpy(dtype=float)
    active_hours = pd.Series(active, index=idx).groupby(idx.month).sum().reindex(range(1, 13), fill_value=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        kw_per_month = np.where(active_hours.to_numpy() > 0, energy / active_hours.to_numpy(), 0.0)

    values = np.where(active, kw_per_month[idx.month - 1], 0.0)
    temp = row.get(C.TEMP_C)
    name = f"waste_heat_{int(round(temp)) if pd.notna(temp) else 'NA'}C [kW]"
    return pd.Series(values, index=idx, name=name)


def energy_profile(row: pd.Series, year: int) -> EnergyProfile:
    series = hourly_profile(row, year)
    start, end = operating_window(row[C.DAILY_HOURS_CLEAN])
    weekend = bool(row["weekend_available"])
    temp = row.get(C.TEMP_C)
    wh = WasteHeatProfile(
        waste_heat_potential_name=str(row[C.SOURCE_NAME]),
        temperature_c=int(round(temp)) if pd.notna(temp) else 0,
        weekend_available=weekend,
        avg_daily_availability_h=float(row[C.DAILY_HOURS_CLEAN]),
        profile_data=series.to_frame(),
        aggregated_demands=float(series.sum()),
        unit_of_output="kWh",
    )
    return EnergyProfile(
        company_name=str(row[C.COMPANY]),
        site_name=str(row[C.SITE]),
        city=None if pd.isna(row[C.CITY]) else str(row[C.CITY]),
        nace_code=str(row.get("nace_code", "") or ""),
        description=str(row.get(C.INFO) or row[C.SOURCE_NAME]),
        production_volume=float(row[C.ANNUAL_KWH_CLEAN]),
        start_time=start,
        end_time=end,
        weekdays=[1, 2, 3, 4, 5, 6, 7] if weekend else [1, 2, 3, 4, 5],
        weekend_days=[] if weekend else [6, 7],
        year=year,
        working_hours={"start": start, "end": end},
        holidays=dict(Germany().holidays(year)),
        waste_heat=wh,
    )


def record_for_plot(row: pd.Series, profile: EnergyProfile) -> SimpleNamespace:
    """Attributes expected by plotting.plot_energy_profile for its info table."""
    s = profile.waste_heat.profile_data.iloc[:, 0]
    active = s.gt(0).groupby(s.index.month).sum().reindex(range(1, 13), fill_value=0).to_numpy()
    energy = row[C.ENERGY_COLS_CLEAN].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        kw = np.where(active > 0, energy / active, 0.0)
    return SimpleNamespace(
        company_name=row[C.COMPANY], site_name=row[C.SITE], street_and_house_number=row.get(C.STREET),
        postal_code=row.get(C.POSTAL_CODE), city=row.get(C.CITY),
        waste_heat_potential_name=row[C.SOURCE_NAME],
        annual_heat_amount_kwh_per_year=float(row[C.ANNUAL_KWH_CLEAN]),
        max_thermal_power_kw=float(row[C.MAX_POWER_KW_CLEAN]),
        avg_temperature_level_c_raw=row.get(C.TEMP_C), temperature_c=row.get(C.TEMP_C),
        avg_daily_availability_h=round(float(row[C.DAILY_HOURS_CLEAN]), 2),
        weekend_availability_raw=row.get(C.WEEKEND), monthly_power_kw=list(kw),
        additional_info_on_waste_heat_potential=row.get(C.INFO),
        annual_working_hours=float(row[C.ANNUAL_HOURS_CLEAN]),
        avg_thermal_power_kw=None,
        logic_of_energy_correction=f"tier {row['quality_tier']} | {row['monthly_source']}",
        llm_category=row.get("LLM_Category"),
    )


def save_profile(row: pd.Series, year: int, output_dir: str | Path, plot: bool = True) -> Path:
    """Write the hourly CSV (and optionally the PNG plot + info table) for one row."""
    from .plotting import plot_energy_profile

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prof = energy_profile(row, year)
    stem = f"waste_heat_profile_row{int(row[C.ROW_ID])}_{year}"
    csv_path = output_dir / f"{stem}.csv"
    prof.waste_heat.profile_data.to_csv(csv_path, index_label="")
    if plot:
        plot_energy_profile(prof, output_dir=str(output_dir), filename=f"{stem}.png",
                            waste_heat_record=record_for_plot(row, prof))
    return csv_path
