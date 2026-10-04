"""Load the pipeline configuration from config.yaml into typed objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass
class Paths:
    raw_file: Path
    raw_sheet: str
    output_dir: Path


@dataclass
class Presence:
    annual_kwh_min: float = 1
    max_power_kw_min: float = 1
    monthly_kw_min: float = 1
    daily_hours_min: float = 0


@dataclass
class Consistency:
    tolerance: float = 0.10
    interpretations: List[str] = field(default_factory=lambda: ["A", "B", "C", "W", "Wh"])
    unmatched_strategy: str = "trust_annual"


@dataclass
class Plausibility:
    temperature_min_c: float = 10
    temperature_max_c: float = 1200
    limit_tolerance: float = 0.05


@dataclass
class BfeeThresholds:
    plant_min_annual_kwh: float = 200_000
    plant_min_hours: float = 1_500
    plant_min_temperature_c: float = 25
    site_min_annual_kwh: float = 800_000


@dataclass
class LlmMedium:
    api_url: str = "https://api.helmholtz-blablador.fz-juelich.de/v1"
    model: str = "alias-large"
    api_key_env: str = "BLABLADOR_API_KEY"


@dataclass
class Config:
    paths: Paths
    calendar_year: int = 2025
    presence: Presence = field(default_factory=Presence)
    consistency: Consistency = field(default_factory=Consistency)
    plausibility: Plausibility = field(default_factory=Plausibility)
    bfee_thresholds: BfeeThresholds = field(default_factory=BfeeThresholds)
    llm_medium: LlmMedium = field(default_factory=LlmMedium)


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read config.yaml. Relative paths are resolved against the project root."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    p = raw["paths"]
    paths = Paths(
        raw_file=PROJECT_ROOT / p["raw_file"],
        raw_sheet=p["raw_sheet"],
        output_dir=PROJECT_ROOT / p["output_dir"],
    )
    cfg = Config(
        paths=paths,
        calendar_year=raw.get("calendar_year", 2025),
        presence=Presence(**raw.get("presence", {})),
        consistency=Consistency(**raw.get("consistency", {})),
        plausibility=Plausibility(**raw.get("plausibility", {})),
        bfee_thresholds=BfeeThresholds(**raw.get("bfee_thresholds", {})),
        llm_medium=LlmMedium(**raw.get("llm_medium", {})),
    )
    if cfg.consistency.unmatched_strategy not in {"trust_annual", "trust_profile"}:
        raise ValueError("consistency.unmatched_strategy must be 'trust_annual' or 'trust_profile'")
    return cfg
