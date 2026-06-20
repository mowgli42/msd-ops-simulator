"""Observed bottleneck inference — aligned with js/capacity-model.js inferObservedBottleneck."""

from __future__ import annotations

from analysis.sim_engine import SimMetrics


def infer_observed_bottleneck(metrics: SimMetrics, *, queue_threshold: int = 3) -> str:
    if metrics.waiting_vehicles > 0:
        return "devices"
    if metrics.offload_queue >= metrics.loading_queue and metrics.offload_queue >= queue_threshold:
        return "offload"
    if metrics.loading_queue > metrics.offload_queue and metrics.loading_queue >= queue_threshold:
        return "loading"
    return "balanced"


def bottlenecks_align(predicted: str, observed: str) -> bool:
    """True when analysis prediction matches sim queues (with allowed equivalents)."""
    if predicted == observed:
        return True
    if predicted == "balanced" and observed == "balanced":
        return True
    # Under stress, sim may show devices while analysis flags offload/loading
    if predicted in ("offload", "loading") and observed == "devices":
        return True
    if predicted == "devices" and observed in ("devices", "offload", "loading"):
        return True
    if predicted == "offload" and observed == "loading":
        return False
    if predicted == "loading" and observed == "offload":
        return False
    return False
