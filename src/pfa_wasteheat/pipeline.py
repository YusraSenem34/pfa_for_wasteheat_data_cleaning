"""Run the full cleaning pipeline.

    python -m pfa_wasteheat.pipeline                # uses config.yaml
    python -m pfa_wasteheat.pipeline --config other.yaml

Every input row is kept. The output has the raw columns unchanged, the cleaned
values in *_clean columns, and one column per flag plus a quality tier.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from . import columns as C
from .config import Config, load_config
from .consistency import add_presence_flags, check_consistency
from .imputation import build_clean_values
from .loading import load_raw, standardize_columns
from .plausibility import add_plausibility_flags
from .quality import assign_quality_tier
from .reporting import summarize, summary_markdown
from .text_cleaning import clean_text_columns

log = logging.getLogger(__name__)


def run(cfg: Config, raw: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Clean the data. `raw` = already loaded German export (e.g. a Streamlit upload)."""
    if raw is None:
        df = load_raw(cfg.paths.raw_file, cfg.paths.raw_sheet)
    else:
        df = standardize_columns(raw)

    df = clean_text_columns(df)
    df = add_presence_flags(df, cfg)
    df = check_consistency(df, cfg)
    df = build_clean_values(df, cfg)
    df = add_plausibility_flags(df, cfg)
    df = assign_quality_tier(df)

    assert len(df) == df[C.ROW_ID].nunique(), "row ids must stay unique"
    return df


def save_outputs(df: pd.DataFrame, cfg: Config) -> dict:
    out = Path(cfg.paths.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "parquet": out / "pfa_cleaned.parquet",
        "excel": out / "pfa_cleaned.xlsx",
        "summary": out / "cleaning_summary.md",
    }
    df.to_parquet(paths["parquet"], index=False)
    df.to_excel(paths["excel"], index=False)
    paths["summary"].write_text(summary_markdown(summarize(df)), encoding="utf-8")
    for p in paths.values():
        log.info("Saved %s", p)
    return paths


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Clean the PfA waste heat register.")
    parser.add_argument("--config", default=None, help="path to a config.yaml")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config) if args.config else load_config()
    df = run(cfg)
    save_outputs(df, cfg)


if __name__ == "__main__":
    main()
