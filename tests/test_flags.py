"""New data-quality checks, and the link between code, definitions and documentation."""

import re

import numpy as np
import pandas as pd
import pytest

from pfa_wasteheat import columns as C
from pfa_wasteheat.definitions import DOC_PATH, END, FLAGS, START, TIERS, render_generated_section
from pfa_wasteheat.pipeline import run

from conftest import energy_A, make_row, to_raw

SEASONAL = [120, 110, 100, 90, 80, 70, 60, 70, 80, 90, 100, 120]
FLAT = [100.0] * 12


def run_rows(cfg, rows, labels=None):
    out = run(cfg, raw=to_raw(list(rows.values())), medium_labels=labels)
    out.index = list(rows)
    return out


# ------------------------------------------------------------------ new checks

def test_rough_estimate_flags(cfg):
    q_flat = energy_A(FLAT, 24, True)  # 100 kW x 8760 h
    rows = {
        "estimate": make_row(annual=q_flat, pmax=100, daily=24, weekend="Ja", monthly=FLAT),
        "real": make_row(annual=energy_A(SEASONAL, 24, True), pmax=150, daily=24, weekend="Ja",
                         monthly=SEASONAL),
    }
    d = run_rows(cfg, rows)
    assert d.loc["estimate", "annual_equals_pmax_x_hours"] and d.loc["estimate", "profile_flat_at_pmax"]
    assert not d.loc["real", "annual_equals_pmax_x_hours"] and not d.loc["real", "profile_flat_at_pmax"]


def test_pmax_far_above_monthly(cfg):
    q = energy_A(SEASONAL, 24, True)
    rows = {
        "watts": make_row(annual=q, pmax=150_000, daily=24, weekend="Ja", monthly=SEASONAL),
        "ok": make_row(annual=q, pmax=150, daily=24, weekend="Ja", monthly=SEASONAL),
    }
    d = run_rows(cfg, rows)
    assert d.loc["watts", "pmax_far_above_monthly"]
    assert not d.loc["ok", "pmax_far_above_monthly"] and not d.loc["ok", "pmax_below_monthly"]


def test_duplicate_values_different_name(cfg):
    base = dict(annual=1_000_000, pmax=200, monthly=None)
    rows = {
        "k1": make_row(source="Kompressor 1", **base),
        "k2": make_row(source="Kompressor 2", **base),
        "other_site": make_row(site="Werk 2", source="Kompressor 3", **base),
    }
    d = run_rows(cfg, rows)
    assert d.loc["k1", "is_duplicate_values"] and d.loc["k2", "is_duplicate_values"]
    assert not d.loc["other_site", "is_duplicate_values"]
    assert not d["is_duplicate_exact"].any()


def test_inactive_months(cfg):
    summer_off = [100] * 6 + [0, 0] + [100] * 4
    rows = {"campaign": make_row(annual=energy_A(summer_off, 24, True), monthly=summer_off, pmax=100)}
    d = run_rows(cfg, rows)
    assert d.loc["campaign", "has_inactive_months"] and d.loc["campaign", "n_active_months"] == 10


def test_daily_hours_never_above_24_without_max_power(cfg):
    # Only annual energy, no weekends: the old logic produced 32 h/day here.
    rows = {"only_annual": make_row(annual=500_000, pmax=0, daily=0, weekend="Nein", monthly=None)}
    d = run_rows(cfg, rows)
    assert d.loc["only_annual", "daily_hours_source"] == "assumed_24h"
    assert d.loc["only_annual", C.DAILY_HOURS_CLEAN] == pytest.approx(24)
    assert not d.loc["only_annual", "daily_hours_impossible"]


def test_medium_flags_and_name_guard(cfg):
    rows = {
        "steam": make_row(source="Dampf", annual=1_000_000, monthly=None, temp=60),
        "water": make_row(source="Kühlwasser", annual=1_000_000, monthly=None, temp=60),
    }
    labels = pd.DataFrame({
        C.ROW_ID: [0, 1],
        C.SOURCE_NAME: ["Dampf", "Some Other Name"],  # 2nd label belongs to another row -> ignored
        "LLM_Category": ["Steam", "Water"],
    })
    d = run_rows(cfg, rows, labels)
    assert d.loc["steam", "steam_below_100c"]
    assert pd.isna(d.loc["water", "LLM_Category"]) and d.loc["water", "medium_unclear"]


# ------------------------------------------------------------------ definitions <-> code <-> docs

BOOL_COLUMNS_THAT_ARE_NOT_FLAGS = {
    "has_annual", "has_max_power", "has_monthly", "has_daily_hours", "has_temperature",
    "weekend_available", "interp_matched", "ctrl_temperature", "ctrl_pressure", "ctrl_feed_in",
    "ctrl_retrofittable", "ctrl_not_retrofittable",
}


def test_every_flag_column_has_a_definition(cfg):
    rows = {"a": make_row(annual=1_000_000, monthly=None), "b": make_row(annual=None, monthly=SEASONAL)}
    labels = pd.DataFrame({C.ROW_ID: [0, 1], C.SOURCE_NAME: ["Kühlwasser"] * 2, "LLM_Category": ["Water"] * 2})
    d = run_rows(cfg, rows, labels)
    bool_cols = {c for c in d.columns if d[c].dtype == bool}
    undocumented = bool_cols - set(FLAGS) - BOOL_COLUMNS_THAT_ARE_NOT_FLAGS
    assert not undocumented, f"add these flags to definitions.py: {sorted(undocumented)}"
    missing_in_output = {f for f in FLAGS if f not in d.columns}
    assert not missing_in_output, f"defined but not produced: {sorted(missing_in_output)}"


def test_tier_rules_refer_to_existing_flags():
    for name, f in FLAGS.items():
        assert f.tier in {"none", "C", "D"}, name
    assert set(TIERS) == {"A", "B", "C", "D"}


def test_doc_is_up_to_date():
    text = DOC_PATH.read_text(encoding="utf-8")
    section = re.search(re.escape(START) + r".*?" + re.escape(END), text, re.S).group(0)
    assert section == render_generated_section(), "run: python -m pfa_wasteheat.definitions"
