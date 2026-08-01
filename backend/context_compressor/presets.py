"""
Named presets that tune target_compression / dedup_threshold /
min_accuracy_floor together, instead of requiring users to reason
about three independent knobs.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str
    target_compression: float
    dedup_threshold: float
    min_accuracy_floor: float
    description: str


PRESETS = {
    "conservative": Preset(
        name="conservative",
        target_compression=0.40,
        dedup_threshold=0.92,
        min_accuracy_floor=0.98,
        description="Light trim -- only removes near-exact repeats and clear filler. "
                     "Best when downstream accuracy matters more than size.",
    ),
    "balanced": Preset(
        name="balanced",
        target_compression=0.70,
        dedup_threshold=0.85,
        min_accuracy_floor=0.95,
        description="Default trade-off -- meets the ~70% reduction target while "
                     "keeping a 95% accuracy guardrail.",
    ),
    "aggressive": Preset(
        name="aggressive",
        target_compression=0.85,
        dedup_threshold=0.75,
        min_accuracy_floor=0.90,
        description="Maximum size reduction for cost/latency-critical paths. "
                     "Higher risk of dropping subtly-relevant context.",
    ),
}


def get_preset(name: str) -> Preset:
    try:
        return PRESETS[name]
    except KeyError:
        valid = ", ".join(PRESETS)
        raise ValueError(f"Unknown preset '{name}'. Valid presets: {valid}")
