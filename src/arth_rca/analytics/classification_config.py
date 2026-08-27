"""
Editable Configuration for Relationship Constraint Classification.
Includes regulatory, safety, and physical keyword dictionaries, duration bands, and thresholds.
"""

from typing import List, Dict, Tuple

# Configurable auto-classification confidence threshold
AUTO_CLASSIFY_THRESHOLD: float = 0.80

# 1. Regulatory Terms -> HARD_REGULATORY (Confidence = 0.90)
HARD_REGULATORY_TERMS: List[str] = [
    "permit",
    "inspection",
    "inspect",
    "approval",
    "sign-off",
    "sign off",
    "ahj",
    "code compliance",
    "hydro test",
    "hydrotest",
    "pressure test",
    "commissioning sign-off",
    "energiz",
    "utility release",
]

# 2. Safety Terms -> HARD_SAFETY (Confidence = 0.90)
HARD_SAFETY_TERMS: List[str] = [
    "loto",
    "lock-out",
    "lockout",
    "tag-out",
    "confined space",
    "scaffold cert",
    "fall protection",
    "excavation permit",
    "shoring",
]

# 3. Physical / Curing Terms -> HARD_PHYSICAL (Confidence = 0.85)
HARD_PHYSICAL_TERMS: List[str] = [
    "cure",
    "cured",
    "curing",
    "dry",
    "dried",
    "drying",
    "initial set",
    "final set",
    "concrete set",
    "grout set",
    "weld",
    "welding",
    "ndt",
    "backfill",
    "compaction",
    "settle",
    "settlement",
    "fireproofing cure",
    "strip form",
    "strike form",
    "de-shore",
    "deshore",
]

# 4. Lag-Duration Correlation Bands in Hours (Supporting signal: +0.15 confidence bump)
CURING_LAG_BANDS_HOURS: Dict[str, Tuple[float, float]] = {
    "concrete_cure": (48.0, 96.0),
    "coating_dry": (24.0, 48.0),
    "fireproofing": (24.0, 72.0),
    "grout_set": (24.0, 48.0),
}
