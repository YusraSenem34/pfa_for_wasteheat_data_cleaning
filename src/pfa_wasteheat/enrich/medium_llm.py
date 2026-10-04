"""Classify the waste heat medium (Water, Exhaust, Steam, ...) with an LLM.

Changes compared with the old categorization_of_wasteheat.py:
- the API key is read from an environment variable, never from the code
- the prompt lists the right number of categories and allows "Unclear"
- the answer must be exactly one category; anything else is stored as "Invalid"
- the raw model reply and the model name are kept for reproducibility
- the client is created only when the function is called (importing is side-effect free)

    export BLABLADOR_API_KEY=...        # Windows PowerShell: $env:BLABLADOR_API_KEY="..."
    python -m pfa_wasteheat.enrich.medium_llm --limit 50
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from .. import columns as C
from ..config import Config, load_config

log = logging.getLogger(__name__)

CATEGORIES = ["Water", "Exhaust", "Steam", "Air", "Oil", "Refrigerant"]
UNCLEAR = "Unclear"

SYSTEM_PROMPT = (
    "You are an expert in industrial processes and waste heat. "
    "Classify the heat carrier (medium) of the waste heat source described by the user. "
    f"Answer with exactly one of these {len(CATEGORIES) + 1} words and nothing else: "
    + ", ".join(CATEGORIES + [UNCLEAR]) + ". "
    f"Use {UNCLEAR} if the description does not allow a confident decision."
)


def parse_reply(reply: Optional[str]) -> str:
    """Accept only an exact category word (case-insensitive, punctuation stripped)."""
    if not isinstance(reply, str):
        return "Invalid"
    word = reply.strip().strip(".!\"'").capitalize()
    return word if word in CATEGORIES + [UNCLEAR] else "Invalid"


def _client(cfg: Config):
    from openai import OpenAI  # imported lazily so the package works without openai installed

    key = os.environ.get(cfg.llm_medium.api_key_env)
    if not key:
        raise RuntimeError(f"Set the environment variable {cfg.llm_medium.api_key_env} first.")
    return OpenAI(api_key=key, base_url=cfg.llm_medium.api_url)


def classify_medium(df: pd.DataFrame, cfg: Config, sleep_s: float = 0.0) -> pd.DataFrame:
    """Return a DataFrame indexed like `df` with LLM_Category, LLM_Raw_Reply, LLM_Model."""
    client = _client(cfg)
    rows = []
    for idx, row in df.iterrows():
        user = (
            f"Waste_Heat_Potential_Name: '{row.get(C.SOURCE_NAME, '')}'\n"
            f"Additional_Info_on_Waste_Heat_Potential: '{row.get(C.INFO, '')}'"
        )
        try:
            resp = client.chat.completions.create(
                model=cfg.llm_medium.model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": user}],
                max_tokens=10,
                temperature=0.0,
            )
            reply = resp.choices[0].message.content
        except Exception as exc:  # network errors etc. - keep going, mark the row
            log.warning("Row %s failed: %s", idx, exc)
            reply = None
        rows.append({"LLM_Category": parse_reply(reply) if reply is not None else "Error",
                     "LLM_Raw_Reply": reply, "LLM_Model": cfg.llm_medium.model})
        if sleep_s:
            time.sleep(sleep_s)
    return pd.DataFrame(rows, index=df.index)


def import_legacy_labels(df: pd.DataFrame, legacy_file: str | Path) -> pd.DataFrame:
    """Re-use labels from the old pipeline (old prompt!), matched by the original Excel row."""
    old = pd.read_excel(legacy_file, usecols=[C.EXCEL_ROW, "LLM_Category"]).drop_duplicates(C.EXCEL_ROW)
    out = df[[C.ROW_ID, C.EXCEL_ROW]].merge(old, on=C.EXCEL_ROW, how="left")
    out["LLM_Raw_Reply"] = None
    out["LLM_Model"] = "legacy (old prompt, 6 categories, no Unclear)"
    return out.drop(columns=[C.EXCEL_ROW])


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="LLM classification of the waste heat medium")
    parser.add_argument("--input", default=None, help="cleaned parquet (default: output of the pipeline)")
    parser.add_argument("--limit", type=int, default=None, help="only the first N rows (for testing)")
    parser.add_argument("--legacy", default=None, help="old Excel file with LLM_Category to re-use instead")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    cfg = load_config()
    src = Path(args.input) if args.input else Path(cfg.paths.output_dir) / "pfa_cleaned.parquet"
    df = pd.read_parquet(src)
    out = Path(cfg.paths.output_dir) / "llm_medium.parquet"
    if args.legacy:
        labels = import_legacy_labels(df, args.legacy)
        labels.to_parquet(out, index=False)
        log.info("Saved %s: %s", out, labels["LLM_Category"].value_counts(dropna=False).to_dict())
        return
    if args.limit:
        df = df.head(args.limit)
    labels = classify_medium(df, cfg)
    pd.concat([df[[C.ROW_ID]], labels], axis=1).to_parquet(out, index=False)
    log.info("Saved %s: %s", out, labels["LLM_Category"].value_counts().to_dict())


if __name__ == "__main__":
    main()
