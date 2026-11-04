"""Versioned prototype policy, not empirically calibrated safety probabilities."""
from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class EnvironmentPolicy:
    version: str = "environment-v1-draft"
    step_m: float = 20.0
    cctv_radius_m: float = 60.0
    lighting_radius_m: float = 40.0
    open_store_radius_m: float = 50.0
    bell_radius_m: float = 200.0
    max_detour_ratio: float = 0.20
    max_extra_minutes: float = 3.0
    score_tolerance: float = 5.0

    def __post_init__(self):
        import math
        values = asdict(self)
        for name, value in values.items():
            if name == "version":
                continue
            if not math.isfinite(value) or value < 0 or (name.endswith("_m") and value == 0):
                raise ValueError(f"Invalid environment policy: {name}")

    def active_factors(self, period: str) -> tuple[str, ...]:
        return ("cctv", "lighting", "open_store", "bell") if period == "night" else ("cctv", "open_store", "bell")

    def radius(self, factor: str) -> float:
        return getattr(self, f"{factor}_radius_m")

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()
