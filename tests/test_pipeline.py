import numpy as np
import pandas as pd
import pytest

from pfa_wasteheat import columns as C
from pfa_wasteheat.energy import month_days, month_working_days
from pfa_wasteheat.enrich.medium_llm import parse_reply
from pfa_wasteheat.pipeline import run
from pfa_wasteheat.plausibility import parse_temperature_range
from pfa_wasteheat.profiles.hourly import hourly_profile

from conftest import YEAR, energy_A, energy_B, make_row, to_raw

SEASONAL = [120, 110, 100, 90, 80, 70, 60, 70, 80, 90, 100, 120]


# ---------------------------------------------------------------- calendar

def test_calendar():
    assert month_days(2024)[1] == 29 and month_days(2025).sum() == 365
    # January 2025: 23 weekdays minus New Year's Day
    assert month_working_days(2025)[0] == 22


# ---------------------------------------------------------------- consistency

@pytest.fixture
def cases(cfg):
    q_a = energy_A(SEASONAL, 16, False)
    rows = {
        "as_reported_A": make_row(annual=q_a, daily=16, weekend="Nein", monthly=SEASONAL, pmax=130),
        "as_reported_B": make_row(annual=energy_B(SEASONAL), daily=8, weekend="Nein", monthly=SEASONAL, pmax=500),
        "monthly_kwh_C": make_row(annual=sum(SEASONAL) * 1000, monthly=[v * 1000 for v in SEASONAL], pmax=2000),
        "watts_W": make_row(annual=q_a, daily=16, weekend="Nein", monthly=[v * 1000 for v in SEASONAL], pmax=130),
        # 24 h on all days: readings A and B coincide, so the only explanation left is "wrong by 5x"
        "inconsistent": make_row(annual=5 * energy_B(SEASONAL), daily=24, weekend="Ja", monthly=SEASONAL, pmax=1000),
        "only_monthly": make_row(annual=None, daily=16, weekend="Nein", monthly=SEASONAL, pmax=130),
        "only_annual": make_row(annual=1_000_000, daily=24, monthly=None, pmax=200),
        "no_daily_hours": make_row(annual=energy_B(SEASONAL), daily=0, monthly=SEASONAL, pmax=130),
        "nothing": make_row(annual=None, monthly=None, pmax=0, daily=0),
        "small": make_row(company="Klein AG", annual=50_000, monthly=None, pmax=10),
    }
    raw = to_raw(list(rows.values()))
    out = run(cfg, raw=raw)
    out.index = list(rows)
    return raw, out


def test_readings_are_recognised(cases):
    _, d = cases
    assert d.loc["as_reported_A", "interp_best"] == "A"
    assert d.loc["as_reported_A", "consistency_status"] == "consistent_as_reported"
    assert d.loc["as_reported_B", "interp_best"] == "B"
    assert d.loc["monthly_kwh_C", "interp_best"] == "C"
    assert d.loc["monthly_kwh_C", "consistency_status"] == "consistent_after_unit_fix"
    assert d.loc["watts_W", "interp_best"] == "W"


def test_quality_tiers(cases):
    _, d = cases
    assert d.loc["as_reported_A", "quality_tier"] == "A"
    assert d.loc["monthly_kwh_C", "quality_tier"] == "B"
    assert d.loc["inconsistent", "quality_tier"] == "C"
    assert d.loc["nothing", "quality_tier"] == "D"


def test_inconsistent_row_is_rescaled_not_forced_silently(cases):
    _, d = cases
    r = d.loc["inconsistent"]
    assert r["was_rescaled"] and r["scale_factor"] == pytest.approx(5, rel=1e-6)
    assert r["consistency_status"] == "inconsistent"


def test_imputation_sources(cases):
    _, d = cases
    assert d.loc["only_monthly", "annual_source"].startswith("from_monthly:A")
    assert d.loc["only_monthly", C.ANNUAL_KWH_CLEAN] == pytest.approx(energy_A(SEASONAL, 16, False))
    assert d.loc["only_annual", "monthly_source"] == "flat_from_annual"
    assert d.loc["no_daily_hours", "daily_hours_source"] == "derived"
    assert d.loc["no_daily_hours", "interp_best"] == "B"  # A needs daily hours, B does not
    assert d.loc["nothing", "no_energy_info"]


def test_monthly_energy_sums_to_annual(cases):
    _, d = cases
    ok = d[C.ANNUAL_KWH_CLEAN].notna()
    total = d.loc[ok, C.ENERGY_COLS_CLEAN].sum(axis=1)
    np.testing.assert_allclose(total, d.loc[ok, C.ANNUAL_KWH_CLEAN], rtol=1e-9)
    np.testing.assert_allclose(d.loc[ok, C.SHARE_COLS_CLEAN].sum(axis=1), 1.0, rtol=1e-9)


def test_no_rows_removed_threshold_only_flagged(cases):
    raw, d = cases
    assert len(d) == len(raw)
    assert d.loc["small", "below_200mwh"] and d.loc["small", "below_plant_threshold"]


def test_raw_numbers_untouched(cases):
    raw, d = cases
    from pfa_wasteheat.loading import standardize_columns
    std = standardize_columns(raw)
    for col in [C.ANNUAL_KWH, C.MAX_POWER_KW, C.DAILY_HOURS] + C.POWER_COLS:
        np.testing.assert_array_equal(d[col].to_numpy(dtype=float), std[col].to_numpy(dtype=float))


# ---------------------------------------------------------------- sites and duplicates

def test_same_site_name_different_companies_not_merged(cfg):
    rows = [make_row(company="Alpha GmbH", site="Werk 1", annual=500_000, monthly=None),
            make_row(company="Beta GmbH", site="Werk 1", annual=500_000, monthly=None)]
    d = run(cfg, raw=to_raw(rows))
    assert d[C.SITE_ID].nunique() == 2
    # each site alone is below 800 MWh; merged by name only they would pass
    assert d["below_site_threshold"].all()


def test_duplicates_flagged(cfg):
    row = make_row(annual=1_000_000, monthly=None)
    d = run(cfg, raw=to_raw([row, row]))
    assert d["is_duplicate_exact"].tolist() == [False, True]
    assert d["quality_tier"].tolist()[1] == "D"


# ---------------------------------------------------------------- helpers

def test_temperature_range_parser():
    assert parse_temperature_range("25 - 60 °c") == (25, 60)
    assert parse_temperature_range(">=110 °c") == (110, np.inf)
    assert parse_temperature_range("<25 °c") == (-np.inf, 25)


def test_llm_reply_parser():
    assert parse_reply(" steam. ") == "Steam"
    assert parse_reply("Unclear") == "Unclear"
    assert parse_reply("The answer is Water") == "Invalid"


def test_hourly_profile_conserves_energy(cases):
    _, d = cases
    for name in ["as_reported_A", "as_reported_B", "inconsistent", "only_annual"]:
        row = d.loc[name]
        s = hourly_profile(row, YEAR)
        assert len(s) == 8760
        assert s.sum() == pytest.approx(row[C.ANNUAL_KWH_CLEAN], rel=1e-9)
        if not row["weekend_available"]:
            assert s[s.index.weekday >= 5].sum() == 0
