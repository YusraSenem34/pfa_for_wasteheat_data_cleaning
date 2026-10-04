"""Small synthetic datasets in the raw (German) column layout."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pfa_wasteheat.config import Config, Paths
from pfa_wasteheat.energy import available_hours, full_month_hours
from pfa_wasteheat.loading import COLUMN_MAPPING

YEAR = 2025
GERMAN = {eng: ger for ger, eng in COLUMN_MAPPING.items()}


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(paths=Paths(raw_file=tmp_path / "none.xlsx", raw_sheet="x", output_dir=tmp_path),
                  calendar_year=YEAR)


def make_row(company="Firma GmbH", site="Werk 1", plz="10115", source="Kühlwasser",
             annual=None, pmax=500.0, temp=60.0, temp_range="60 - 90 °c", daily=24,
             weekend="Ja", monthly=None):
    monthly = [0.0] * 12 if monthly is None else list(monthly)
    row = {
        "Company_Name": company, "Site_Name": site, "Street_and_House_Number": "Hauptstr. 1",
        "Postal_Code": plz, "City": "Berlin", "Waste_Heat_Potential_Name": source,
        "Annual_Heat_Amount_kWh_per_Year": 0.0 if annual is None else annual,
        "Max_Thermal_Power_kW": pmax, "Avg_Temperature_Level_C": temp, "Temperature_Range": temp_range,
        "Avg_Daily_Availability_h": daily, "Weekend_Availability": weekend,
        "Availability": "rest", "Availability_Predictability": "Ja",
        "Existing_Control_Options": "TEMPERATUR, NACHRUESTBAR",
        "Additional_Info_on_Waste_Heat_Potential": None,
    }
    for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                           "August", "September", "October", "November", "December"]):
        row[f"Power_Profile_{m}_kW"] = monthly[i]
    return row


def to_raw(rows) -> pd.DataFrame:
    """English test rows -> German headers, as the Excel export would deliver them."""
    return pd.DataFrame(rows).rename(columns=GERMAN)


def energy_A(monthly, daily, weekend_bool):
    return float((np.array(monthly) * available_hours(np.array([daily]), np.array([weekend_bool]), YEAR)[0]).sum())


def energy_B(monthly):
    return float((np.array(monthly) * full_month_hours(YEAR)).sum())
