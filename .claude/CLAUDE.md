# CLAUDE.md

Notes for anyone (people or AI assistants) who picks up this repository: what it is,
what was done, why, and what is still open. For the user-facing guide see
[README.md](README.md); for every flag and tier see [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).

## What this project is

Data cleaning for the German **Plattform für Abwärme (PfA)** register of industrial waste
heat sources, run by BAFA / BfEE under § 17 EnEfG. Input: the Excel export dated
13.05.2025 (22,198 rows, sheet `Abwärmepotentiale`).

It is the data-preparation part of Yüsra Senem's Master's thesis (MSc Data Science,
BHT Berlin, with DLR): *"Predicting Industrial Waste Heat Profiles from Sector
Classification: A Data-Driven Approach for German Companies"*. The cleaned file from
this repo is the input of a **separate thesis project** (statistics, visualisation,
modelling). That work does not belong here.

## Ground rules (please keep them)

1. **Never delete a row.** Problems become flag columns and a quality tier (A-D).
   Which rows to use is decided later, in the modelling step.
2. **Never overwrite a raw value.** Cleaned values go into new `*_clean` columns;
   `*_source` columns say where each cleaned value came from.
3. **Every number that changes results lives in `config.yaml`** (tolerances, thresholds,
   calendar year, paths), not in the code.
4. **No API keys in the code or in git.** Keys are read from environment variables
   (`BLABLADOR_API_KEY`, later `LUMIS_API_KEY`); `.env` is in `.gitignore`.
   An old Blablador key exists in the history of `main` and must be considered revoked.
5. **Flags and tiers are defined in one place**: `src/pfa_wasteheat/definitions.py`.
   After changing it, run `python -m pfa_wasteheat.definitions` to regenerate the
   reference section of `docs/DATA_QUALITY.md` (a test fails if the doc is out of date).
6. Ask the data owner before adding new flags, rules or features. Several ideas were
   deliberately postponed (see "Open items").

## How to run

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\Activate
pip install -r requirements.txt && pip install -e .

python -m pfa_wasteheat.pipeline                      # -> data/processed/pfa_cleaned.{parquet,xlsx} + cleaning_summary.md
python -m pfa_wasteheat.enrich.geocode --legacy data/data_with_coordinates_all_latest.xlsx
                                                      # -> pfa_cleaned_geo.{parquet,xlsx}; --no-online = no OpenStreetMap requests
streamlit run apps/cleaning_app.py                    # flags, tiers, tolerance slider
streamlit run apps/geo_app.py                         # map, radius search, hourly profile of one row
pytest                                                # 27 tests
```

The raw Excel goes to `data/raw/pfa_datenpraesentation.xlsx`. Everything in
`data/processed/` is generated and not in git.

First-time setup after cloning:

1. Create and activate the virtual environment, install the requirements and
   `pip install -e .` (commands above).
2. Put the raw export into `data/raw/` (it is not in git).
3. Run the pipeline, then `pytest` to check that everything works.
4. Optional: geocoding (needs internet), LLM medium classification (needs an API key
   in an environment variable, never in a file that is committed).

## Claude Code settings

`.claude/settings.json` is shared through git, so everyone who opens the repo with
Claude Code gets the same permissions:

- **Allowed without asking:** tests, the pipeline, regenerating the flag docs,
  offline geocoding, installing the requirements, read-only git commands.
- **Asks first:** online geocoding and LLM calls (slow / use an API), and git commands
  that change history or the remote (commit, push, checkout, merge, reset, rm).
- **Never allowed:** reading `.env` files, editing the raw data (`data/raw/` and the
  Excel files directly in `data/`), force-pushing.

No hooks are configured. Personal additions go into `.claude/settings.local.json`,
which is ignored by git.

## Pipeline in short

`pipeline.run()`: load → clean text → presence flags → check whether the annual energy
was given in MWh → consistency check → build clean values (imputation) → plausibility
flags → medium flags (only if `data/processed/llm_medium.parquet` exists) → quality tier.

**The central problem:** the register asks for 12 monthly "power in kW" values, but
reporters filled them in in different ways. Each row is tested against 7 readings,
each converted to monthly energy (kWh) and compared with the reported annual energy:

| Reading | Meaning |
|---|---|
| A | kW while the source is available (daily hours × available days) |
| B | kW averaged over the whole month (24 h × days in month) |
| C | already kWh per month |
| W / MW | values in W (÷1000) / MW (×1000), otherwise like A |
| Wh / MWh | monthly energy in Wh (÷1000) / MWh (×1000) |

Tolerance: 10 % for calendar-based readings (A, B, W, MW), 2 % for pure energy readings
(C, Wh, MWh). The closest reading wins, but A or B is preferred when it fits. If nothing
fits, the shape is rescaled to the reported annual energy (`was_rescaled`, tier C).

Missing values are filled by 5 rules (replacing the old cases 1-16) in `imputation.py`;
the 12 months always sum exactly to `annual_kwh_clean`. Daily hours that are not
reported come from annual ÷ (max power × available days), otherwise 24 h is assumed
(`assumed_24h`), so derived values never exceed 24 h/day.

**Quality tiers:** D = not usable as a target (no energy info, physically impossible,
exact duplicate); C = rescaled or filled in; B = consistent after a unit fix;
A = consistent as reported. BfEE thresholds (200 MWh, 1,500 h, 25 °C, 800 MWh per site)
are only flagged; `site_id` = company + site + postal code.

Results on the 13.05.2025 export: A 10,019 · B 3,055 · C 8,330 · D 794 rows;
about 224.7 TWh in total. Agreed for modelling: **leave tier D out**.

## Repository map

```
config.yaml                     all settings
src/pfa_wasteheat/
  pipeline.py                   entry point
  loading.py                    read Excel, English column names, drop contact data
                                (Email, Phone, Additional_Notes)
  text_cleaning.py              names/addresses, company_id, site_id
  energy.py, consistency.py     readings and the annual-vs-monthly check
  imputation.py                 *_clean values and *_source columns
  plausibility.py, quality.py   flags and tiers
  definitions.py                meaning of every flag and tier (single source of truth)
  reporting.py                  cleaning_summary.md
  enrich/geocode.py             Nominatim geocoding with cache; re-uses old coordinates
  enrich/medium_llm.py          LLM classification of the heat medium (Water, Steam, ...)
  profiles/hourly.py            8760 h profile of one row (replaces waste_heat_generator.py)
apps/                           Streamlit apps
docs/DATA_QUALITY.md            full explanation of the cleaning, flag and tier reference
tests/
```

The old modules `profile.py` and `waste_heat_generator.py` live only on branch `main`.

## History

- `main`: first version (cases 1-16, rows deleted, key in the code).
- `restructure`: the rewrite described here. Main changes: no row deletion, no
  overwriting, all readings tested in both unit directions (W/Wh/MW/MWh and annual in
  MWh), rescaling recorded instead of counted as a match, flag registry plus generated
  docs, tests, config file, geocoding cache, energy-conserving hourly profiles.

## Open items

- **Medium classification with an LLM:** Blablador is no longer available. Planned
  switch to the BHT Lumis API (`https://lumis-api.bht-berlin.de/v1`, OpenAI-compatible),
  waiting for an API key via the supervisor. When it arrives: change `llm_medium` in
  `config.yaml` and read the key from `LUMIS_API_KEY`; also store the model name the API
  returns per row.
- **NACE codes:** plan is to assign them by hand for a sample and predict the rest
  (4-digit) with an LLM. Not started in this repo.
- **Address quality (postponed):** about 94 sites have a postal code that does not exist
  as an area code, about 17 sites lie more than 50 km from their postal code centre (same
  town name in another region), and 225 sites share coordinates. Possible later work:
  geo-quality flags, a hand-checked sample, better geocoding.
- **Calendar year:** `calendar_year: 2025` is used; the register may describe 2024
  operation. Confirm with the supervisor.
- **Additional_Notes** is dropped in `loading.py`; it may be useful as LLM input later.

## Environment notes

- `workalendar` depends on `PyMeeus`, which may fail to build. Installing `pymeeus`
  first, then `workalendar --no-deps`, works.
- Geocoding sends 1 request per second to OpenStreetMap; results are cached in
  `data/processed/geocode_cache.parquet`, so an interrupted run continues where it stopped.
- Streamlit charts: avoid column names with square brackets (e.g. `[kW]`); some versions
  then draw an empty chart.