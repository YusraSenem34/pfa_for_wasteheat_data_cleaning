"""Load the raw PfA Excel export and give it English column names."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import IO, Union

import pandas as pd

from . import columns as C

log = logging.getLogger(__name__)

# German header (whitespace normalised to "_") -> English name
COLUMN_MAPPING = {
    "Firmenname": C.COMPANY,
    "Standortname": C.SITE,
    "Straße_und_Hausnummer": C.STREET,
    "PLZ": C.POSTAL_CODE,
    "Ort": C.CITY,
    "Name_des_Abwärmepotentials": C.SOURCE_NAME,
    "Wärmemenge_pro_Jahr_(in_kWh/a)": C.ANNUAL_KWH,
    "Maximale_thermische_Leistung_(in_kW)": C.MAX_POWER_KW,
    "Durchschnittliches_Temperaturniveau_(in_°C)": C.TEMP_C,
    "Temperaturbereich": C.TEMP_RANGE,
    "Durchschnittliche_tägl._Verfügbarkeit_(in_h)": C.DAILY_HOURS,
    "Verfügbarkeit_am_Wochenende": C.WEEKEND,
    "Verfügbarkeit": C.AVAILABILITY,
    "Vorhersehbarkeit_der_Verfügbarkeit": C.PREDICTABILITY,
    "Vorhandene_Regelungsmöglichkeiten": C.CONTROL_OPTIONS,
    "Ergänzende_Informationen_zum_Abwärmepotential": C.INFO,
    "E-Mail-Adresse": "Email_Address",
    "Telefonnummer": "Phone_Number",
    "Weitere_Hinweise": "Additional_Notes",
}
_GERMAN_MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                  "August", "September", "Oktober", "November", "Dezember"]
COLUMN_MAPPING.update({
    f"Leistungsprofil_{de}_(in_kW)": col for de, col in zip(_GERMAN_MONTHS, C.POWER_COLS)
})

# Contact data is not needed for the analysis and is personal data -> dropped on load.
DROP_COLUMNS = ["Email_Address", "Phone_Number", "Additional_Notes"]

NUMERIC_COLUMNS = [C.ANNUAL_KWH, C.MAX_POWER_KW, C.TEMP_C, C.DAILY_HOURS] + C.POWER_COLS


def read_raw_excel(source: Union[str, Path, IO], sheet: str = "Abwärmepotentiale") -> pd.DataFrame:
    """Read the export exactly as published (German number format, PLZ as text)."""
    return pd.read_excel(
        source,
        sheet_name=sheet,
        skiprows=1,          # first row holds section titles, second row the headers
        decimal=",",
        thousands=".",
        dtype={"PLZ": str},
    )


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename German headers to English, drop contact columns, add row identifiers."""
    df = df.copy()
    df.columns = [re.sub(r"\s+", "_", str(c).replace("\n", " ").replace("\r", " ").strip())
                  for c in df.columns]
    df = df.rename(columns=COLUMN_MAPPING)

    missing = [c for c in [C.COMPANY, C.ANNUAL_KWH, C.DAILY_HOURS, C.WEEKEND] + C.POWER_COLS
               if c not in df.columns]
    if missing:
        raise ValueError(f"Input file is missing expected columns: {missing}")

    df = df.drop(columns=[c for c in DROP_COLUMNS if c in df.columns])
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.reset_index(drop=True)
    df.insert(0, C.ROW_ID, df.index)
    df.insert(1, C.EXCEL_ROW, df.index + 3)  # header is on Excel row 2, data starts on row 3
    return df


def load_raw(source: Union[str, Path, IO], sheet: str = "Abwärmepotentiale") -> pd.DataFrame:
    df = standardize_columns(read_raw_excel(source, sheet))
    log.info("Loaded %d rows from %s", len(df), getattr(source, "name", source))
    return df
