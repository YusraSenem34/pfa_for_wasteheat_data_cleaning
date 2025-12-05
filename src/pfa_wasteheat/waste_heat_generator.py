#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate hourly waste-heat profiles from Hamburg_wasteheat_export.csv

For every data row in the input CSV a separate output CSV is created with:
- hourly resolution for a full calendar year (8760 hours)
- one column containing the waste-heat power in kW
- the temperature level (°C) embedded in the column and file name

The following input columns are used:
- Temperature_Range          -> used to derive a single max temperature in °C
- Power_Profile_XXX_kW      -> monthly power levels in kW (Jan..Dec)
- Avg_Daily_Availability_h  -> average operating hours per day
- Weekend_Availability      -> whether weekends & holidays are also available

Holidays are taken from workalendar's Germany calendar.

This module is intentionally independent from the main demand generator
and uses pydantic models for robust parsing/validation.
"""

from __future__ import annotations

import argparse
import datetime
import math
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from workalendar.europe import Germany



# Add the project root to the Python path so absolute imports work when run as a script
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.energy_profile_generator.profile import EnergyProfile, WasteHeatProfile
from src.energy_profile_generator.plotter import plot_energy_profile

class WasteHeatRecord(BaseModel):
    """Representation of a single waste-heat row from the Hamburg export."""

    company_name: str = Field(alias="Company_Name")
    site_name: str = Field(alias="Site_Name")
    street_and_house_number: Optional[str] = Field(
        default=None, alias="Street_and_House_Number"
    )
    postal_code: Optional[Union[str, int]] = Field(default=None, alias="Postal_Code")
    city: str = Field(alias="City")
    waste_heat_potential_name: str = Field(alias="Waste_Heat_Potential_Name")

    annual_heat_amount_kwh_per_year: Optional[float] = Field(
        default=None, alias="Annual_Heat_Amount_kWh_per_Year"
    )
    max_thermal_power_kw: Optional[float] = Field(
        default=None, alias="Max_Thermal_Power_kW"
    )
    avg_temperature_level_c_raw: Optional[float] = Field(
        default=None, alias="Avg_Thermal_Power"
    )

    temperature_c: int = Field(alias="Temperature_Range")

    # Availability information
    avg_daily_availability_h: float = Field(alias="Avg_Daily_Availability_h")
    weekend_availability_raw: str = Field(alias="Weekend_Availability")

    # Monthly power profiles in kW
    p_jan_kw: float = Field(alias="Power_Profile_January_kW")
    p_feb_kw: float = Field(alias="Power_Profile_February_kW")
    p_mar_kw: float = Field(alias="Power_Profile_March_kW")
    p_apr_kw: float = Field(alias="Power_Profile_April_kW")
    p_may_kw: float = Field(alias="Power_Profile_May_kW")
    p_jun_kw: float = Field(alias="Power_Profile_June_kW")
    p_jul_kw: float = Field(alias="Power_Profile_July_kW")
    p_aug_kw: float = Field(alias="Power_Profile_August_kW")
    p_sep_kw: float = Field(alias="Power_Profile_September_kW")
    p_oct_kw: float = Field(alias="Power_Profile_October_kW")
    p_nov_kw: float = Field(alias="Power_Profile_November_kW")
    p_dec_kw: float = Field(alias="Power_Profile_December_kW")

    additional_info_on_waste_heat_potential: Optional[str] = Field(
        default=None, alias="Additional_Info_on_Waste_Heat_Potential"
    )
    original_excel_row: Optional[int] = Field(
        default=None, alias="Original_Excel_Row"
    )
    annual_energy_months: Optional[float] = Field(
        default=None, alias="Annual_Energy_Months"
    )
    diff_annual_energy_months: Optional[float] = Field(
        default=None, alias="Diff_Annual_Energy_Months"
    )
    match_annual_energy_months: Optional[bool] = Field(
        default=None, alias="Match_Annual_Energy_Months"
    )
    annual_working_hours: Optional[float] = Field(
        default=None, alias="Annual_Working_Hours"
    )
    avg_thermal_power_kw: Optional[float] = Field(
        default=None, alias="AVG_Thermal_Power"
    )
    logic_of_energy_correction: Optional[str] = Field(
        default=None, alias="Logic_of_Energy_Correction"
    )
    llm_category: Optional[str] = Field(default=None, alias="LLM_Category")
    full_address: Optional[str] = Field(default=None, alias="full_address")
    location: Optional[str] = Field(default=None, alias="location")
    lat: Optional[float] = Field(default=None, alias="lat")
    long: Optional[float] = Field(default=None, alias="long")
    distance_km: Optional[float] = Field(default=None, alias="distance_km")
    radius_viz: Optional[float] = Field(default=None, alias="radius_viz")

    model_config = ConfigDict(validate_by_name=True)

    @field_validator("temperature_c", mode="before")
    def parse_temperature(cls, v: object) -> int:
        """
        Extract the *maximum* temperature from the Temperature_Range string.

        Examples:
            "60 - 90 °c"   -> 90
            ">=110 °c"     -> 110
            "<25 °c"       -> 25
        """
        s = str(v)
        numbers = re.findall(r"-?\d+\.?\d*", s.replace(",", "."))
        if not numbers:
            raise ValueError(f"Could not parse temperature from '{s}'")
        max_val = max(float(x) for x in numbers)
        return int(round(max_val))

    @field_validator("weekend_availability_raw", mode="before")
    def normalize_weekend_flag(cls, v: object) -> str:
        return str(v).strip()

    @field_validator("postal_code", mode="before")
    def normalize_postal_code(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        # Accept ints / floats and cast to string; treat NaN as None
        if isinstance(v, float) and math.isnan(v):
            return None
        return str(v)

    @field_validator("logic_of_energy_correction", mode="before")
    def normalize_logic_of_energy_correction(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return str(v)

    @field_validator("additional_info_on_waste_heat_potential", mode="before")
    def normalize_additional_info(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return str(v)

    @property
    def weekend_available(self) -> bool:
        """Return True if waste heat is available on weekends/holidays."""
        return self.weekend_availability_raw.lower().startswith("ja")

    @property
    def monthly_power_kw(self) -> List[float]:
        """Return list of monthly power setpoints in kW, Jan..Dec."""
        return [
            self.p_jan_kw,
            self.p_feb_kw,
            self.p_mar_kw,
            self.p_apr_kw,
            self.p_may_kw,
            self.p_jun_kw,
            self.p_jul_kw,
            self.p_aug_kw,
            self.p_sep_kw,
            self.p_oct_kw,
            self.p_nov_kw,
            self.p_dec_kw,
        ]


def _calculate_working_hours_from_record(record: WasteHeatRecord) -> tuple[int, int, List[int], List[int]]:
    """
    Calculate working hours configuration from WasteHeatRecord.
    
    Args:
        record: WasteHeatRecord instance
        
    Returns:
        tuple: (start_time, end_time, weekdays, weekend_days)
    """
    # Default start time (8 AM)
    start_time = 8
    
    # Calculate end_time from Avg_Daily_Availability_h
    # Round to nearest integer hour
    daily_availability = float(record.avg_daily_availability_h or 0.0)
    if daily_availability > 16:
        start_time = 0
    end_time = start_time + int(round(daily_availability))
    
    # Ensure end_time doesn't exceed 24
    if end_time > 24:
        end_time = 24
    
    # Determine weekdays and weekend_days based on Weekend_Availability
    if record.weekend_available:
        # Available on all days including weekends
        weekdays = [1, 2, 3, 4, 5, 6, 7]  # All days
        weekend_days = []  # No distinction needed
    else:
        # Only weekdays
        weekdays = [1, 2, 3, 4, 5]  # Monday to Friday
        weekend_days = [6, 7]  # Saturday and Sunday
    
    return start_time, end_time, weekdays, weekend_days


def _setup_calendar(year: int) -> tuple[Dict[datetime.date, str], pd.DataFrame]:
    """Create holidays dict and empty hourly DataFrame for a full year."""
    cal = Germany()
    holidays = dict(cal.holidays(year))
    energy_demand = pd.DataFrame(
        index=pd.date_range(
            datetime.datetime(year, 1, 1, 0),
            periods=8760,
            freq="h",
        )
    )
    return holidays, energy_demand


def _slugify(text: str, max_length: int = 80) -> str:
    """Create a filesystem-friendly slug."""
    text = re.sub(r"[^\w]+", "_", text.strip(), flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    if max_length and len(text) > max_length:
        text = text[:max_length].rstrip("_")
    return text or "waste_heat"


def _build_hourly_profile(
    record: WasteHeatRecord, year: int, start_time: int, end_time: int
) -> pd.Series:
    """
    Build an hourly power profile (kW) for a single record.

    Logic:
    - For each month, the monthly Power_Profile_XXX_kW value is used as the
      hourly kW value for all working hours in that month.
    - Working hours are defined by start_time to end_time (e.g., 8 to 16).
    - If weekend availability is "nein", weekends and German public holidays
      are set to zero.
    - Hours outside working hours are set to zero.
    - No daily availability scaling is applied - the monthly setpoint is the
      actual hourly value during working hours.
    """
    # Setup calendar and base index identical to the main generator logic
    holidays_dict, energy_demand = _setup_calendar(year)
    idx = energy_demand.index

    # Initialize all values to zero
    values = pd.Series(0.0, index=idx)
    
    # Get holiday dates set for quick lookup
    holiday_dates = {d for d in holidays_dict.keys()}
    
    # Process each month
    for month in range(1, 13):
        month_mask = idx.month == month
        month_indices = idx[month_mask]
        
        if month_indices.empty:
            continue
        
        # Get the monthly power setpoint (this is the hourly kW value for working hours)
        month_power = float(record.monthly_power_kw[month - 1])
        
        if month_power <= 0:
            # No power requested for this month, keep at zero
            continue
        
        # For each hour in this month
        for ts in month_indices:
            date = ts.date()
            hour = ts.hour
            
            # Check if this is a working day
            is_weekend = ts.weekday() >= 5  # Saturday=5, Sunday=6
            is_holiday = date in holiday_dates
            
            # Determine if this hour should have power
            should_have_power = False
            
            if record.weekend_available:
                # Available on weekends and holidays
                # Check if within working hours
                if start_time <= hour < end_time:
                    should_have_power = True
            else:
                # Not available on weekends/holidays
                if not is_weekend and not is_holiday:
                    # Check if within working hours
                    if start_time <= hour < end_time:
                        should_have_power = True
            
            # Set the value
            if should_have_power:
                values[ts] = month_power
            else:
                values[ts] = 0.0

    series_name = f"waste_heat_{record.temperature_c} [kW]"
    return pd.Series(values.values, index=idx, name=series_name)


def _default_output_filename(record: WasteHeatRecord, year: int) -> str:
    """
    Create a descriptive filename that includes the temperature.

    Example:
        Waste_heat_profile_90C_Hamburg_H_R_Oelwerke_Schindler_Gmbh_Waermetauscher_22Tc204Abc.csv
    """
    base = f"{record.city}_{record.company_name}_{record.waste_heat_potential_name}"
    slug = _slugify(base)
    return f"Waste_heat_profile_{record.temperature_c}C_{year}_{slug}.csv"



def generate_waste_heat_profile(record: WasteHeatRecord, year: int) -> EnergyProfile:
    # Calculate working hours from record
    start_time, end_time, weekdays, weekend_days = _calculate_working_hours_from_record(record)

    # Build hourly profile
    series = _build_hourly_profile(record, year, start_time, end_time)

    # Give the series a descriptive, unique column name for the aggregated CSV
    series_column_name = f"{record.temperature_c}C_{_slugify(record.waste_heat_potential_name, max_length=40)}"
    series = series.rename(series_column_name)
    all_series.append(series)

    # Wrap in EnergyProfile with nested WasteHeatProfile metadata
    working_hours = {
        "start": start_time,
        "end": end_time,
        "weekdays": weekdays,
        "weekend_days": weekend_days,
    }
    profile_df = series.to_frame()
    # Calculate aggregated demand (sum of hourly values in kWh)
    aggregated_demand = float(series.sum())  # Already in kW, sum gives kWh
    
    waste_heat_meta = WasteHeatProfile(
        waste_heat_potential_name=record.waste_heat_potential_name,
        temperature_c=record.temperature_c,
        weekend_available=record.weekend_available,
        avg_daily_availability_h=record.avg_daily_availability_h,
        profile_data=profile_df,
        aggregated_demands=aggregated_demand,
        unit_of_output="kWh",
    )
    energy_profile = EnergyProfile(
        company_name=record.company_name,
        site_name=record.site_name,
        city=record.city,
        nace_code="",
        description=record.additional_info_on_waste_heat_potential
        or record.waste_heat_potential_name,
        production_volume=record.annual_heat_amount_kwh_per_year or 0.0,
        start_time=start_time,
        end_time=end_time,
        weekdays=weekdays,
        weekend_days=weekend_days,
        year=year,
        working_hours=working_hours,
        holidays=holidays_dict,
        waste_heat=waste_heat_meta,
    )
    return energy_profile



def generate_waste_heat_profiles(
    input_csv: Path,
    output_dir: Path,
    year: int = 2025,
) -> Dict[int, Path]:
    """
    Generate hourly waste-heat profile CSVs for all rows in the input file.

    Args:
        input_csv: Path to the input CSV file
        output_dir: Directory where output files will be saved
        year: Calendar year for which to generate profiles

    Returns:
        Mapping from row index (0-based) to created file path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_csv)

    created_files: Dict[int, Path] = {}
    all_series: list[pd.Series] = []
    holidays_dict, _ = _setup_calendar(year)

    # Process all rows
    for row_idx, row in df.iterrows():
        try:
            record = WasteHeatRecord(**row.to_dict())
        except ValidationError as exc:
            # Skip problematic rows but continue processing others
            print(f"[waste_heat_generator] Skipping row {row_idx} due to validation error:")
            print(exc)
            continue

        energy_profile = generate_waste_heat_profile(record, year)

        # # Calculate working hours from record
        # start_time, end_time, weekdays, weekend_days = _calculate_working_hours_from_record(record)

        # # Build hourly profile
        # series = _build_hourly_profile(record, year, start_time, end_time)

        # # Give the series a descriptive, unique column name for the aggregated CSV
        # series_column_name = f"{record.temperature_c}C_{_slugify(record.waste_heat_potential_name, max_length=40)}"
        # series = series.rename(series_column_name)
        # all_series.append(series)

        # # Wrap in EnergyProfile with nested WasteHeatProfile metadata
        # working_hours = {
        #     "start": start_time,
        #     "end": end_time,
        #     "weekdays": weekdays,
        #     "weekend_days": weekend_days,
        # }
        # profile_df = series.to_frame()
        # # Calculate aggregated demand (sum of hourly values in kWh)
        # aggregated_demand = float(series.sum())  # Already in kW, sum gives kWh
        
        # waste_heat_meta = WasteHeatProfile(
        #     waste_heat_potential_name=record.waste_heat_potential_name,
        #     temperature_c=record.temperature_c,
        #     weekend_available=record.weekend_available,
        #     avg_daily_availability_h=record.avg_daily_availability_h,
        #     profile_data=profile_df,
        #     aggregated_demands=aggregated_demand,
        #     unit_of_output="kWh",
        # )
        # energy_profile = EnergyProfile(
        #     company_name=record.company_name,
        #     site_name=record.site_name,
        #     city=record.city,
        #     nace_code="",
        #     description=record.additional_info_on_waste_heat_potential
        #     or record.waste_heat_potential_name,
        #     production_volume=record.annual_heat_amount_kwh_per_year or 0.0,
        #     start_time=start_time,
        #     end_time=end_time,
        #     weekdays=weekdays,
        #     weekend_days=weekend_days,
        #     year=year,
        #     working_hours=working_hours,
        #     holidays=holidays_dict,
        #     waste_heat=waste_heat_meta,
        # )
        # Determine CSV and PNG filenames (unique per waste-heat record)
        out_file = output_dir / _default_output_filename(record, year)
        png_name = out_file.with_suffix(".png").name

        # Create and save plot for this waste-heat profile in the same directory as CSVs
        plot_energy_profile(energy_profile, output_dir=str(output_dir), filename=png_name, waste_heat_record=record)

        # Match example_output.csv layout: empty index label, one value column
        # series.to_frame().to_csv(out_file, index_label="")

        created_files[row_idx] = out_file

    # After processing all rows, also write a single CSV containing all series
    if all_series:
        all_df = pd.concat(all_series, axis=1)
        # Use input file name plus 'series' as requested, stored into the same output directory
        combined_name = f"{input_csv.stem}_series.csv"
        combined_path = output_dir / combined_name
        all_df.to_csv(combined_path, index_label="")
        print(f"[waste_heat_generator] Combined series CSV saved to '{combined_path.resolve()}'")

    return created_files


def _parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate hourly waste-heat profiles from Hamburg_wasteheat_export.csv",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Calendar year for which to generate 8760 hourly values",
    )
    return parser.parse_args(args=list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = _parse_args(argv)
    # Use fixed input and output paths as requested
    input_csv = Path("Hamburg_wasteheat_export.csv")
    output_dir = Path("examples")

    created = generate_waste_heat_profiles(
        input_csv=input_csv,
        output_dir=output_dir,
        year=args.year,
    )

    print(
        f"[waste_heat_generator] Generated {len(created)} profile file(s) in '{output_dir.resolve()}'"
    )


if __name__ == "__main__":
    main()
