"""Summary tables of a pipeline run (for the thesis data-quality chapter and the app)."""

from __future__ import annotations

from typing import Dict

import pandas as pd

from . import columns as C
from .definitions import FLAGS, TIERS

FLAG_COLUMNS = list(FLAGS)


def _counts(s: pd.Series, name: str) -> pd.DataFrame:
    out = s.value_counts(dropna=False).rename_axis(name).reset_index(name="rows")
    out["share_%"] = (100 * out["rows"] / len(s)).round(1)
    return out


def summarize(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    tier = df.groupby("quality_tier").agg(
        rows=(C.ROW_ID, "size"),
        companies=(C.COMPANY_ID, "nunique"),
        energy_TWh=(C.ANNUAL_KWH_CLEAN, lambda s: round(s.sum() / 1e9, 1)),
    ).reset_index()
    tier["share_%"] = (100 * tier["rows"] / len(df)).round(1)
    tier["meaning"] = tier["quality_tier"].map(lambda t: TIERS[t].name)

    present = [f for f in FLAG_COLUMNS if f in df.columns]
    flags = pd.DataFrame({
        "flag": present,
        "group": [FLAGS[f].group for f in present],
        "rows": [int(df[f].fillna(False).sum()) for f in present],
    })
    flags["share_%"] = (100 * flags["rows"] / len(df)).round(1)
    flags["tier_effect"] = [FLAGS[f].tier for f in present]
    flags["meaning"] = [FLAGS[f].meaning for f in present]

    scale = df.loc[df["was_rescaled"], "scale_factor"]
    scale_bins = pd.cut(scale, [0, 0.1, 0.5, 0.9, 1.1, 2, 10, float("inf")]).value_counts().sort_index()
    scale_tbl = scale_bins.rename_axis("scale_factor").reset_index(name="rows")
    scale_tbl["scale_factor"] = scale_tbl["scale_factor"].astype(str)

    return {
        "overview": pd.DataFrame({
            "metric": ["rows", "companies", "sites", "annual energy (TWh, clean)"],
            "value": [len(df), df[C.COMPANY_ID].nunique(), df[C.SITE_ID].nunique(),
                      round(df[C.ANNUAL_KWH_CLEAN].sum() / 1e9, 1)],
        }),
        "quality_tiers": tier,
        "consistency_status": _counts(df["consistency_status"], "consistency_status"),
        "best_interpretation": _counts(df.loc[df["interp_matched"], "interp_best"], "interp_best (matched rows)"),
        "monthly_source": _counts(df["monthly_source"], "monthly_source"),
        "flags": flags,
        "rescale_factors": scale_tbl,
    }


def summary_markdown(tables: Dict[str, pd.DataFrame]) -> str:
    parts = ["# Cleaning summary\n",
             "Counts from the last pipeline run. What each flag and tier means: docs/DATA_QUALITY.md\n"]
    for name, tbl in tables.items():
        parts.append(f"## {name.replace('_', ' ').capitalize()}\n")
        parts.append(tbl.to_markdown(index=False))
        parts.append("")
    return "\n".join(parts)
