"""Definitions of all quality flags and tiers - the single source of truth.

Used by
- quality.py      (which flags put a row into tier C or D)
- reporting.py    (summary tables with descriptions)
- apps/cleaning_app.py (flag guide)
- docs/DATA_QUALITY.md (the flag reference section is generated from here:
                        python -m pfa_wasteheat.definitions)

When you add a flag to the pipeline, add it here too - a test checks that every
flag column the pipeline produces has a definition.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .config import PROJECT_ROOT


@dataclass(frozen=True)
class Flag:
    group: str
    meaning: str        # plain-language: what it says about the row
    rule: str           # exact condition used in the code
    why: str            # why it matters for the analysis
    tier: str = "none"  # "D", "C" or "none" - effect on the quality tier
    optional: bool = False  # only present when enrichment data (LLM labels) exists


GROUPS = [
    "Consistency of annual energy and monthly profile",
    "Changes made by the pipeline",
    "Profile shape",
    "Physical plausibility",
    "Reporting style (rough estimates)",
    "Duplicates",
    "BfEE de-minimis thresholds",
    "Heat medium (needs LLM labels)",
]

FLAGS: Dict[str, Flag] = {
    # ------------------------------------------------------------------ consistency
    "interp_ambiguous": Flag(
        group=GROUPS[0],
        meaning="More than one explanation fits, so the unit the reporter meant is not certain.",
        rule="At least two different readings (A, B, C, W, Wh, MW, MWh) are within their tolerance of the "
             "reported annual energy (A and B count as one when the source runs 24 h on all days, because "
             "then they are the same calculation) - or W/Wh fits but there is no max power to decide "
             "whether the monthly values or the annual energy have the wrong unit.",
        why="The chosen reading may be wrong. For W/Wh without max power this matters a lot: if in fact "
            "the annual energy was given in MWh, the true energy is 1000 times larger.",
    ),
    "annual_in_mwh": Flag(
        group=GROUPS[0],
        meaning="The annual energy was given in MWh instead of kWh. It is multiplied by 1000 in "
                "annual_kwh_clean, and the readings of the monthly columns are tested against the "
                "corrected value.",
        rule="Reported annual energy / max power < 8.76 h × 1.05 (the source would deliver its whole "
             "year's energy in a few hours), reported annual < annual_mwh_max_reported_kwh (200 MWh), "
             "max power ≤ annual_mwh_max_power_kw (100 MW), and after × 1000 at least "
             "annual_mwh_min_flh_after (50) full-load hours.",
        why="Without this check the source would stay 1000 times too small (e.g. 2,765 kWh/a for a "
            "cooling system with 848 kW). The size limits keep apart the other explanation - max "
            "power and monthly values both in W, annual correct - which gives the same full-load hours.",
    ),
    # ------------------------------------------------------------------ changes
    "was_rescaled": Flag(
        group=GROUPS[1],
        meaning="Annual energy and monthly profile contradict each other under every reading. The monthly "
                "values were scaled so that they add up to the reported annual energy.",
        rule="Annual energy and monthly values both reported, no reading within the tolerance "
             "(consistency_status = inconsistent) and unmatched_strategy = trust_annual. The shape comes "
             "from the base reading (A, B or C) of the closest reading. scale_factor = reported (or "
             "corrected) annual energy / recalculated annual energy under the closest reading.",
        why="Either the annual value or the profile is wrong, and we cannot tell which. The shape of "
            "the months is kept, but their level is an assumption. Check scale_factor: values far from 1 "
            "(e.g. < 0.1 or > 10) mean a large correction.",
        tier="C",
    ),
    "was_imputed": Flag(
        group=GROUPS[1],
        meaning="At least one of the four key values was missing and has been filled in by calculation.",
        rule="One or more of: monthly profile, annual energy, max power, daily hours was not reported "
             "(see has_* columns) and was derived. imputed_fields lists which ones; the *_source "
             "columns say how (e.g. daily_hours_source = derived_from_max_power or assumed_24h).",
        why="Filled-in values contain no new information - they are calculated from the other fields. "
            "Never use a filled-in value as a prediction target (e.g. a flat profile created from the "
            "annual energy says nothing about seasonality).",
        tier="C",
    ),
    "no_energy_info": Flag(
        group=GROUPS[1],
        meaning="Not enough information to estimate any energy for this source.",
        rule="No annual energy, no monthly profile, and not both max power and daily hours.",
        why="annual_kwh_clean is empty. The row can still be counted (e.g. number of sources per "
            "company) but has no energy value.",
        tier="D",
    ),
    # ------------------------------------------------------------------ profile shape
    "is_flat_profile_raw": Flag(
        group=GROUPS[2],
        meaning="The reporter entered the same value for all 12 months.",
        rule="Monthly values reported and all 12 values identical.",
        why="Often a sign that no monthly data was available and one number was copied 12 times. "
            "Such profiles carry no information about seasonality (about 37 % of all rows).",
    ),
    "is_flat_profile_clean": Flag(
        group=GROUPS[2],
        meaning="The clean monthly profile is flat - either reported flat or filled in flat by the pipeline.",
        rule="is_flat_profile_raw, or monthly_source is flat_from_annual / flat_from_max_power.",
        why="Use this to separate 'really constant' from 'seasonal' profiles when predicting profile "
            "shape.",
    ),
    "has_inactive_months": Flag(
        group=GROUPS[2],
        meaning="The reported profile has at least one month with no waste heat (e.g. a summer or "
                "Christmas shutdown).",
        rule="Monthly values reported and at least one month is 0. n_active_months counts the months "
             "with a value > 0.",
        why="Not an error - real operating pattern. Useful as a profile feature and for finding "
            "seasonal or campaign operation (e.g. sugar factories).",
    ),
    # ------------------------------------------------------------------ plausibility
    "temp_implausible": Flag(
        group=GROUPS[3],
        meaning="The average temperature is outside a realistic range for industrial waste heat.",
        rule="Avg_Temperature_Level_C < temperature_min_c (10 °C) or > temperature_max_c (1200 °C), "
             "see config.yaml.",
        why="Likely a typing error (e.g. 1 °C or 1925 °C). Temperature decides how the heat can be "
            "used, so a wrong value makes the row unusable.",
        tier="D",
    ),
    "temp_range_mismatch": Flag(
        group=GROUPS[3],
        meaning="The average temperature does not fall into its own temperature category.",
        rule="Avg_Temperature_Level_C outside the bounds of Temperature_Range (±1 K).",
        why="Consistency check. In the 2025 release this never happens, because the platform "
            "computes Temperature_Range from the temperature. Do not use both as model inputs.",
    ),
    "pmax_below_monthly": Flag(
        group=GROUPS[3],
        meaning="The reported maximum power is lower than the power in at least one month - "
                "a maximum cannot be lower than a monthly value.",
        rule="Max power and daily hours reported and peak_monthly_kw > Max_Thermal_Power_kW × 1.05. "
             "peak_monthly_kw = highest monthly power while the source is available, from the best reading.",
        why="Max power or the profile is wrong. Be careful when using max power or full-load hours "
            "as targets.",
    ),
    "pmax_far_above_monthly": Flag(
        group=GROUPS[3],
        meaning="The reported maximum power is more than 100 times the highest monthly power.",
        rule="Max power, daily hours and monthly values reported and Max_Thermal_Power_kW > "
             "pmax_far_above_factor (100) × peak_monthly_kw.",
        why="Peaks can be higher than monthly averages, but not by a factor of 100 or more. Most "
            "likely the max power was entered in W instead of kW, or as an energy. Full-load hours of "
            "these rows are then far too low.",
    ),
    "flh_impossible": Flag(
        group=GROUPS[3],
        meaning="Full-load hours are longer than a year: the source would have to run at its maximum "
                "power for more hours than the year has.",
        rule="full_load_hours = annual_kwh_clean / max_power_kw_clean > 8760 h × 1.05 "
             "(8784 h in leap years).",
        why="Physically impossible - the annual energy is too high or the max power too low (often a "
            "unit mix-up). At least one of the two numbers is wrong, so the row is not used as a target.",
        tier="D",
    ),
    "flh_exceeds_availability": Flag(
        group=GROUPS[3],
        meaning="Full-load hours are longer than the hours in which the source is said to be available.",
        rule="full_load_hours > annual_operating_hours_clean × 1.05, where annual operating hours = "
             "daily hours × available days.",
        why="Weaker form of flh_impossible: possible only if the availability information "
            "(daily hours, weekend) is wrong. Worth checking, but not excluded.",
    ),
    "daily_hours_impossible": Flag(
        group=GROUPS[3],
        meaning="The calculated daily availability is more than 24 hours.",
        rule="daily_hours_clean > 24 × 1.05. Can only happen when daily hours were not reported and "
             "were derived from the max power: annual energy / (max power × available days).",
        why="The annual energy is more than the source could deliver at full power, 24 h a day, on "
            "its available days - annual energy and max power do not fit together. Same problem as "
            "flh_impossible, for sources without weekend availability.",
        tier="D",
    ),
    # ------------------------------------------------------------------ reporting style
    "annual_equals_pmax_x_hours": Flag(
        group=GROUPS[4],
        meaning="The annual energy is exactly max power × operating hours - the reporter most likely "
                "estimated it by assuming full load all the time.",
        rule="Annual energy and max power reported and |annual / (max power × annual_operating_hours_clean) − 1| "
             "< 1 %.",
        why="A rough estimate, not a measurement. Such values tend to overestimate the energy. Useful "
            "for sensitivity analyses (model with / without rough estimates).",
    ),
    "profile_flat_at_pmax": Flag(
        group=GROUPS[4],
        meaning="All 12 monthly values equal the maximum power - the profile was filled in with the "
                "maximum, not with real monthly values.",
        rule="is_flat_profile_raw and |monthly value / max power − 1| < 1 %.",
        why="No seasonal information, and it assumes full power all year. Together with "
            "annual_equals_pmax_x_hours the strongest sign of a rough estimate.",
    ),
    # ------------------------------------------------------------------ duplicates
    "is_duplicate_exact": Flag(
        group=GROUPS[5],
        meaning="An exact copy of an earlier row (same company, site, source name and all numbers).",
        rule="All identifying and numeric columns equal to an earlier row. The first occurrence is not "
             "flagged, only the copies.",
        why="Double counting. Copies are excluded so each source is counted once.",
        tier="D",
    ),
    "is_duplicate_name": Flag(
        group=GROUPS[5],
        meaning="The same source name occurs more than once at the same site.",
        rule="Same site_id and Waste_Heat_Potential_Name in more than one row (all rows of the group "
             "flagged). duplicate_group gives the group number.",
        why="Can be legitimate (e.g. 'Kompressor' reported twice for two machines) or a copy with "
            "small changes. Check the group before excluding anything.",
    ),
    "is_duplicate_values": Flag(
        group=GROUPS[5],
        meaning="At the same site, another source has exactly the same numbers but a different name.",
        rule="Same site_id and identical reported annual energy, max power, temperature, daily hours, "
             "weekend availability and 12 monthly values; not an exact duplicate.",
        why="Often identical machines (e.g. three identical compressors), sometimes copy-paste. "
            "In model evaluation, keep such rows in the same fold (group by company or site) - "
            "otherwise the model is tested on rows it has already seen.",
    ),
    # ------------------------------------------------------------------ BfEE thresholds
    "below_200mwh": Flag(
        group=GROUPS[6],
        meaning="The source has less than 200 MWh waste heat per year.",
        rule="annual_kwh_clean < plant_min_annual_kwh (200,000 kWh).",
        why="Below the BfEE reporting limit for a single source - reported voluntarily or by mistake. "
            "Kept, because small sources are closest to the companies the model should predict for.",
    ),
    "below_1500h": Flag(
        group=GROUPS[6],
        meaning="The source is available less than 1,500 hours per year.",
        rule="annual_operating_hours_clean < plant_min_hours (1,500 h).",
        why="Below the BfEE limit. Note: uses the (possibly derived) operating hours, not a reported value.",
    ),
    "below_25c": Flag(
        group=GROUPS[6],
        meaning="The average temperature is below 25 °C.",
        rule="Avg_Temperature_Level_C < plant_min_temperature_c (25 °C).",
        why="Below the BfEE limit; such heat is only usable with a heat pump.",
    ),
    "below_plant_threshold": Flag(
        group=GROUPS[6],
        meaning="The source is below at least one BfEE limit for single sources.",
        rule="below_200mwh or below_1500h or below_25c.",
        why="Summary of the three single-source limits.",
    ),
    "below_site_threshold": Flag(
        group=GROUPS[6],
        meaning="The whole site has less than 800 MWh waste heat per year.",
        rule="Sum of annual_kwh_clean over the sources of the site that pass the single-source limits "
             "< site_min_annual_kwh (800,000 kWh). site_total_kwh holds the sum. A site = company + "
             "site name + postal code.",
        why="Below the BfEE site limit.",
    ),
    "below_bfee_threshold": Flag(
        group=GROUPS[6],
        meaning="The row would have been removed by the BfEE de-minimis rules.",
        rule="below_plant_threshold or below_site_threshold.",
        why="These rows are NOT removed. Use the flag to compare models with and without them.",
    ),
    # ------------------------------------------------------------------ medium
    "medium_unclear": Flag(
        group=GROUPS[7],
        meaning="The LLM could not assign a heat medium.",
        rule="LLM_Category is missing, Unknown, Unclear, Invalid or Error.",
        why="Rows without a medium cannot use it as a model input.",
        optional=True,
    ),
    "steam_below_100c": Flag(
        group=GROUPS[7],
        meaning="The source is labelled as steam, but its average temperature is below 100 °C.",
        rule="LLM_Category = Steam and Avg_Temperature_Level_C < 100 °C.",
        why="Steam at normal pressure is at least 100 °C. Below that it is more likely condensate, "
            "vapour (Brüden) or a wrong LLM label. Good candidates for checking the LLM labels by hand.",
        optional=True,
    ),
}


@dataclass(frozen=True)
class Tier:
    name: str
    meaning: str
    rule: str
    use: str


TIERS: Dict[str, Tier] = {
    "A": Tier(
        name="Consistent as reported",
        meaning="Annual energy and monthly profile agree in the unit the platform asked for (kW). "
                "Nothing was filled in and nothing is physically impossible.",
        rule="consistency_status = consistent_as_reported (best reading A or B within the tolerance), "
             "no tier-C flag, no tier-D flag.",
        use="The most reliable rows. Use alone for a strict check of the main results.",
    ),
    "B": Tier(
        name="Consistent after a unit fix",
        meaning="Annual energy and monthly profile agree once an obvious unit mistake is corrected: "
                "monthly values given as kWh per month (C), in W, Wh, MW or MWh, or the annual energy "
                "given in MWh.",
        rule="consistency_status = consistent_after_unit_fix, no tier-C flag, no tier-D flag.",
        use="As reliable as A once converted - the correction is explained by a unit, not guessed. "
            "Main analysis: A + B.",
    ),
    "C": Tier(
        name="Usable, but corrected or completed",
        meaning="Annual energy and profile contradict each other (the profile was rescaled), or at "
                "least one of the key values was missing and filled in.",
        rule="was_rescaled or was_imputed, and no tier-D flag.",
        use="Fine for counting and totals (e.g. energy per region). For model targets use only the "
            "values that were reported: check *_source and imputed_fields. Sensitivity analysis: A + B + C.",
    ),
    "D": Tier(
        name="Not usable as a model target",
        meaning="No energy information, physically impossible values, or an exact copy of another row.",
        rule="Any of: no_energy_info, temp_implausible, flh_impossible, daily_hours_impossible, "
             "is_duplicate_exact. quality_reasons lists which.",
        use="Exclude from model training and evaluation. Keep in the data so the numbers in the "
            "thesis add up to the original register.",
    ),
}

TIER_ORDER = ["D", "C", "A", "B"]  # precedence: D beats C beats A/B


def flags_for_tier(tier: str) -> List[str]:
    return [name for name, f in FLAGS.items() if f.tier == tier]


# ---------------------------------------------------------------------------- docs

DOC_PATH = PROJECT_ROOT / "docs" / "DATA_QUALITY.md"
START = "<!-- GENERATED:FLAGS START - edit src/pfa_wasteheat/definitions.py, then run python -m pfa_wasteheat.definitions -->"
END = "<!-- GENERATED:FLAGS END -->"


_IDENT = re.compile(r"(?<![`\w*])(\*?(?:[A-Za-z][A-Za-z0-9]*)?(?:_[A-Za-z0-9*]+)+\*?)(?![`\w])")


def code_names(text: str) -> str:
    """Wrap identifiers such as scale_factor or has_* in backticks for Markdown."""
    return _IDENT.sub(r"`\1`", text)


def _cell(text: str) -> str:
    return code_names(text).replace("|", "\\|").replace("\n", " ")


def flags_markdown() -> str:
    lines = []
    for group in GROUPS:
        members = [(n, f) for n, f in FLAGS.items() if f.group == group]
        if not members:
            continue
        lines.append(f"### {group}\n")
        for name, f in members:
            tier = {"D": "→ tier **D**", "C": "→ tier **C**"}.get(f.tier, "no effect on the tier")
            opt = " *(only when LLM labels are available)*" if f.optional else ""
            lines.append(f"#### `{name}`{opt}\n")
            lines.append(f"{code_names(f.meaning)}\n")
            lines.append(f"- **Rule:** {code_names(f.rule)}")
            lines.append(f"- **Why it matters:** {code_names(f.why)}")
            lines.append(f"- **Quality tier:** {tier}\n")
    return "\n".join(lines).rstrip() + "\n"


def tiers_markdown() -> str:
    rows = ["| Tier | Name | Meaning | Rule | How to use |", "|---|---|---|---|---|"]
    for key, t in TIERS.items():
        rows.append(f"| **{key}** | {_cell(t.name)} | {_cell(t.meaning)} | {_cell(t.rule)} | {_cell(t.use)} |")
    return "\n".join(rows) + "\n"


def render_generated_section() -> str:
    return (f"{START}\n\n## 6. Quality tiers\n\n{tiers_markdown()}\n"
            f"Precedence: a row with any tier-D flag is D, otherwise any tier-C flag makes it C, "
            f"otherwise its consistency status decides between A and B.\n\n"
            f"## 7. Flag reference\n\n{flags_markdown()}\n{END}")


def update_doc(path: Path = DOC_PATH) -> bool:
    """Replace the generated section in the doc. Returns True if the file changed."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise ValueError(f"Markers not found in {path}")
    new = pattern.sub(lambda _: render_generated_section(), text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Regenerate the flag reference in docs/DATA_QUALITY.md")
    parser.parse_args(argv)
    changed = update_doc()
    print(f"{DOC_PATH} {'updated' if changed else 'already up to date'}")


if __name__ == "__main__":
    main()
