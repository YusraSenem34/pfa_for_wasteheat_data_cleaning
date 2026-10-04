"""Normalise text columns (addresses, names, categories) and build company/site ids.

Text columns are normalised in place (formatting only). Numeric raw columns are
never touched here.
"""

from __future__ import annotations

import logging

import pandas as pd

from . import columns as C

log = logging.getLogger(__name__)

_NULL_STRINGS = {"", "nan", "none", "<na>"}


def _as_text(s: pd.Series) -> pd.Series:
    """String dtype that keeps missing values as <NA> (astype(str) would turn them into 'nan')."""
    out = s.astype("string").str.strip()
    return out.mask(out.str.lower().isin(_NULL_STRINGS))


def clean_city(s: pd.Series) -> pd.Series:
    s = _as_text(s)
    s = s.str.replace(r"^(DE|D|E)[\s-]*(\d)", r"\2", regex=True, case=False)  # "D-86983 X" -> "86983 X"
    s = s.str.replace(r"^(\d{5})[_\s-]*(.*)$", r"\2", regex=True)              # "38642 Goslar" -> "Goslar"
    s = s.str.split(",").str[0]                                                # "Aalen, Daimlerstr." -> "Aalen"
    s = s.str.split("/").str[0]                                                # "Achim/Embsen" -> "Achim"
    s = s.str.split(r"\s+OT\s+", regex=True).str[0]                            # "X OT Y" -> "X"
    junk = [r"^An der ", r"^Im ", r"^Auf der ", r"^Straße\s", r"\bunbekannt\b", r"\bsiehe\b"]
    s = s.mask(s.str.contains("|".join(junk), case=False, na=False))
    s = s.str.replace(r"[\r\n\t_]+", " ", regex=True).str.replace(r"\s+", " ", regex=True)
    return _as_text(s.str.title())


def clean_street(s: pd.Series) -> pd.Series:
    s = _as_text(s)
    s = s.str.replace(r"[\r\n\t_]+", " ", regex=True)
    s = s.mask(s.str.contains("Postfach|unbekannt|keine Angabe|siehe", case=False, na=False))
    s = s.str.replace(r"str\.", "straße", regex=True, case=False)
    s = s.str.replace(r"Bismarkstrasse", "Bismarckstraße", regex=True, case=False)
    # "Firma GmbH Hauptstr. 1" -> "Hauptstr. 1": drop everything up to a legal-form word
    legal = r"Gmbh|AG|KG|Stiftung|Co\."
    s = s.str.replace(rf"^(.*?)(\b({legal})\b)(.*)$", r"\4", regex=True, case=False)
    s = s.str.replace("Ã", "ß", regex=False)  # encoding artefact seen in the export
    s = s.str.replace(r"\s+", " ", regex=True)
    return _as_text(s.str.title())


def clean_postal_code(s: pd.Series) -> pd.Series:
    return _as_text(s).str.extract(r"(\d{5})", expand=False)


def clean_name(s: pd.Series) -> pd.Series:
    s = _as_text(s)
    s = s.str.replace(r"[/\\_]+", " ", regex=True)
    s = s.str.replace(r"[\r\n\t]+", " ", regex=True)
    s = s.str.replace(r"\s+", " ", regex=True)
    return _as_text(s.str.title())


def _id_part(s: pd.Series) -> pd.Series:
    """Lower-case, alphanumeric-only key part; missing -> empty string."""
    return s.fillna("").str.lower().str.replace(r"[^0-9a-zäöüß]+", "", regex=True)


def clean_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[C.CITY] = clean_city(df[C.CITY])
    df[C.STREET] = clean_street(df[C.STREET])
    df[C.POSTAL_CODE] = clean_postal_code(df[C.POSTAL_CODE])
    for col in [C.COMPANY, C.SITE, C.SOURCE_NAME]:
        df[col] = clean_name(df[col])

    for col in [C.TEMP_RANGE, C.WEEKEND, C.AVAILABILITY, C.PREDICTABILITY, C.CONTROL_OPTIONS]:
        df[col] = _as_text(df[col]).str.lower()

    if C.INFO in df.columns:
        df[C.INFO] = _as_text(_as_text(df[C.INFO]).str.replace(r"\s+", " ", regex=True))

    # --- Derived, analysis-friendly columns ---
    df["weekend_available"] = df[C.WEEKEND].str.startswith("ja").fillna(False).astype(bool)

    ctrl = df[C.CONTROL_OPTIONS].fillna("")
    df["ctrl_temperature"] = ctrl.str.contains("temperatur")
    df["ctrl_pressure"] = ctrl.str.contains("druck")
    df["ctrl_feed_in"] = ctrl.str.contains("einspeisung")
    df["ctrl_retrofittable"] = ctrl.str.contains(r"(?<!nicht_)nachruestbar", regex=True)
    df["ctrl_not_retrofittable"] = ctrl.str.contains("nicht_nachruestbar")

    # --- Identifiers ---
    # company_id groups all rows of one company; site_id = company + site + postal code,
    # so two different companies with a site called "Werk 1" are NOT merged.
    df[C.COMPANY_ID] = _id_part(df[C.COMPANY])
    df[C.SITE_ID] = df[C.COMPANY_ID] + "|" + _id_part(df[C.SITE]) + "|" + df[C.POSTAL_CODE].fillna("")

    log.info("Text cleaned: %d companies, %d sites", df[C.COMPANY_ID].nunique(), df[C.SITE_ID].nunique())
    return df
