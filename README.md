# PfA Waste Heat Data Cleaning

Cleaning and quality flagging of the German *Plattform für Abwärme* (PfA) register
of industrial waste heat potentials (§ 17 EnEfG). Part of a Master's thesis at
BHT Berlin in cooperation with DLR.

**Principle: the pipeline never deletes a row and never overwrites a reported value.**
Raw columns stay exactly as published. Cleaned values go into new `*_clean`
columns, every decision is recorded in a flag column, and each row gets a
quality tier. Which rows to use is decided later, in the modelling step, and can
be varied for sensitivity analyses.

**What every flag and tier means, why it is set, and how the old cases 1-16 map to the
new rules: [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).**

## Quick start

```bash
python -m venv venv
source venv/bin/activate                 # Windows: venv\Scripts\Activate
pip install -r requirements.txt
pip install -e .                         # makes `pfa_wasteheat` importable

python -m pfa_wasteheat.pipeline         # -> data/processed/pfa_cleaned.{parquet,xlsx}
                                         #    + data/processed/cleaning_summary.md
pytest                                   # run the tests
```

Optional enrichment (needs internet / API key):

```bash
# Coordinates: re-use the old geocoding results, then geocode only what is missing
python -m pfa_wasteheat.enrich.geocode --legacy data/data_with_coordinates_all_latest.xlsx

# Medium (Water, Exhaust, Steam, ...) via LLM - key from the environment, never from the code
export BLABLADOR_API_KEY=...             # PowerShell: $env:BLABLADOR_API_KEY="..."
python -m pfa_wasteheat.enrich.medium_llm --limit 50
```

Apps:

```bash
streamlit run apps/cleaning_app.py       # flags, tiers, tolerance slider, downloads
streamlit run apps/geo_app.py            # map, radius search, hourly profiles
```

All settings (calendar year, tolerances, thresholds, paths) are in `config.yaml`.

## Pipeline steps

| Step | Module | What it does |
|---|---|---|
| 1 | `loading.py` | Read the Excel export, English column names, drop contact data, add `row_id` |
| 2 | `text_cleaning.py` | Normalise addresses/names, parse control options, build `company_id` and `site_id` |
| 3 | `consistency.py` | Which fields are reported; test **all** readings of the monthly columns against the annual energy |
| 4 | `imputation.py` | Build the `*_clean` values; fill missing fields and record where each value came from |
| 5 | `plausibility.py` | Physical limits, duplicates, BfEE thresholds (flag only) |
| 6 | `quality.py` | Combine flags into a quality tier A-D |
| 7 | `reporting.py` | Summary tables (also written to `cleaning_summary.md`) |

### Readings of the monthly columns

The register asks for monthly "power profiles in kW", but reporters filled them in
differently. Every reading is converted to monthly **energy** (kWh) and compared
with the reported annual energy (tolerance in `config.yaml`: ±10 % for A, B, W, MW;
±2 % for C, Wh, MWh, where a unit error gives an exact factor). Before that, the annual
energy itself is checked for being given in MWh (`annual_in_mwh`):

| Reading | Meaning | Monthly energy |
|---|---|---|
| A | kW while the source is available | value × daily hours × available days |
| B | kW averaged over the whole month | value × 24 h × days in month |
| C | monthly energy in kWh | value |
| W | W instead of kW | value / 1000 × daily hours × available days |
| Wh | monthly energy in Wh | value / 1000 |
| MW | MW instead of kW | value × 1000 × daily hours × available days |
| MWh | monthly energy in MWh | value × 1000 |

The closest reading wins, but A or B (unit as reported) is preferred whenever it fits.
If nothing fits, the shape of the closest reading is rescaled to the reported annual
energy (`unmatched_strategy: trust_annual`) and the row is flagged `was_rescaled`.

### Quality tiers

| Tier | Meaning |
|---|---|
| **A** | Annual energy and monthly profile agree as reported (reading A or B), nothing filled in |
| **B** | Agree after an explained unit fix (C, W, Wh) |
| **C** | Usable, but rescaled or partly filled in |
| **D** | Not usable as a target: no energy information, physically impossible, or exact duplicate |

### Output columns

| Column group | Examples |
|---|---|
| Raw (unchanged) | `Annual_Heat_Amount_kWh_per_Year`, `Power_Profile_<Month>_kW`, ... |
| Identifiers | `row_id`, `Original_Excel_Row`, `company_id`, `site_id` |
| Clean values | `annual_kwh_clean`, `energy_<Month>_kwh_clean`, `share_<Month>`, `max_power_kw_clean`, `daily_hours_clean`, `full_load_hours` |
| Where a value came from | `monthly_source`, `annual_source`, `max_power_source`, `daily_hours_source`, `imputed_fields` |
| Consistency | `consistency_status`, `interp_best`, `interp_ratio`, `ratio_A` ... `ratio_Wh` |
| Flags (True/False) | 27 flags - see [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md#7-flag-reference) |
| Result | `quality_tier`, `quality_reasons` |

Flag and tier definitions live in `src/pfa_wasteheat/definitions.py`. After changing them, run
`python -m pfa_wasteheat.definitions` to update the documentation (a test checks that it is current).

## Project structure

```
config.yaml                    all settings
data/raw/                      the published Excel export
data/processed/                generated outputs (not in git)
src/pfa_wasteheat/
  pipeline.py                  run everything: python -m pfa_wasteheat.pipeline
  loading.py  text_cleaning.py  consistency.py  imputation.py
  plausibility.py  quality.py  reporting.py  energy.py  columns.py  config.py
  definitions.py               meaning of every flag and tier (single source of truth)
  enrich/geocode.py            Nominatim geocoding with cache
  enrich/medium_llm.py         LLM classification of the heat medium
  profiles/hourly.py           hourly (8760 h) profile per row, energy-conserving
  profiles/models.py, plotting.py
apps/cleaning_app.py, geo_app.py
docs/DATA_QUALITY.md           how the cleaning works, flag and tier reference
tests/
```

## Changes compared with the first version (branch `main`)

- No rows are deleted. Former deletions (cases 1-6, BfEE filters) are now flags / tier D.
- Raw values are never overwritten; cleaned values live in `*_clean` columns.
- All readings of the monthly columns are tested per row and the best one is chosen
  (before: the first fitting unit fix won, and reading B was not tested).
- The forced scaling to the annual energy is recorded (`was_rescaled`, `scale_factor`)
  and lowers the quality tier instead of counting as a match.
- Cases 1-16 replaced by one rule table (`imputation.py`); daily hours are no longer rounded.
- Site threshold uses company + site + postal code (before: site name only, which merged
  different companies' sites such as "Werk 1").
- Bug fixes: case 16 marked case-15 rows as resolved; missing text became the string "Nan";
  the profile generator read the temperature from `AVG_Thermal_Power` and used 8760 h in leap years.
- API key removed from the code (read from `BLABLADOR_API_KEY`).
- Cleaning core no longer imports Streamlit/plotting; settings in `config.yaml`; logging instead of print; tests added.

## Authors

- **Yusra Senem** (yuesra.senem@dlr.de) - primary developer
- DLR (Deutsches Zentrum für Luft- und Raumfahrt) - project sponsor

## License

MIT
