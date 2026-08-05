"""Prometheus-style metrics for ToolKinetik (P1.5).

Lightweight in-memory counters without external dependencies.
Exposed via GET /metrics in Prometheus text format.
"""

from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()

# Counters: {metric_name: {labels_tuple: count}}
_counters: dict[str, dict[tuple, int]] = defaultdict(lambda: defaultdict(int))

# Metric descriptions
_METRIC_HELP = {
    "skill_promote_total": "Total number of skill promotions (by success/failure)",
    "llm_call_total": "Total number of LLM API calls",
}

# Per-metric label names (order must match the tuple used in record_* functions).
_METRIC_LABELS: dict[str, list[str]] = {
    "skill_promote_total": ["skill_name", "success"],
    "llm_call_total": ["model", "success"],
}


def record_skill_promote(skill_name: str, success: bool) -> None:
    """Record a skill promotion attempt."""
    with _lock:
        _counters["skill_promote_total"][(skill_name, str(success).lower())] += 1


def record_llm_call(model: str, success: bool) -> None:
    """Record an LLM API call."""
    with _lock:
        _counters["llm_call_total"][(model, str(success).lower())] += 1


def get_metrics_text() -> str:
    """Return metrics in Prometheus text format."""
    lines: list[str] = []
    with _lock:
        for metric_name, labels_dict in _counters.items():
            help_text = _METRIC_HELP.get(metric_name, "")
            if help_text:
                lines.append(f"# HELP {metric_name} {help_text}")
            lines.append(f"# TYPE {metric_name} counter")
            label_names = _METRIC_LABELS.get(metric_name, [])
            for labels, value in labels_dict.items():
                if labels and label_names:
                    label_parts = [f'{name}="{val}"' for name, val in zip(label_names, labels)]
                    label_str = "{" + ",".join(label_parts) + "}"
                else:
                    label_str = ""
                lines.append(f"{metric_name}{label_str} {value}")
    return "\n".join(lines) + "\n" if lines else ""


def reset_metrics() -> None:
    """Clear all metrics (for tests)."""
    with _lock:
        _counters.clear()


def extract_llm_usage(response: object) -> dict[str, int | None]:
    """Extract token usage from an LLM API response object.

    Returns a dict with prompt_tokens, completion_tokens, total_tokens.
    If the response has no .usage attribute, returns empty dict.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"total_tokens": None}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }