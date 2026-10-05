"""Combine all flags into one quality tier per row (A, B, C, D).

Which flags lead to tier C or D is defined in definitions.py (Flag.tier), together
with the meaning of every tier. Flags without a tier effect (e.g. pmax_below_monthly,
below_bfee_threshold) stay available as separate columns for sensitivity analyses.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .definitions import flags_for_tier

log = logging.getLogger(__name__)

TIER_D_FLAGS = flags_for_tier("D")
TIER_C_FLAGS = flags_for_tier("C")


def assign_quality_tier(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def reasons(cols):
        flags = df[cols].fillna(False).astype(bool)
        return flags.apply(lambda r: ",".join(r.index[r]), axis=1), flags.any(axis=1)

    d_reasons, is_d = reasons(TIER_D_FLAGS)
    c_reasons, is_c = reasons(TIER_C_FLAGS)
    status = df["consistency_status"]

    df["quality_tier"] = np.select(
        [is_d,
         is_c,
         status.eq("consistent_as_reported"),
         status.eq("consistent_after_unit_fix")],
        ["D", "C", "A", "B"],
        default="C",  # e.g. not testable but nothing filled in - should not happen
    )
    df["quality_reasons"] = np.where(is_d, d_reasons, np.where(is_c, c_reasons, ""))

    log.info("Quality tiers: %s", df["quality_tier"].value_counts().sort_index().to_dict())
    return df
