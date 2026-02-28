"""Telemetry helpers for enrichment adapter-chain rollout.

Keeps response tracing/persistence formatting separate from Flask route code so
logic can be unit-tested in isolation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _safe_latency(value: Any) -> float:
    try:
        parsed = float(value)
        if parsed < 0:
            return 0.0
        return parsed
    except (TypeError, ValueError):
        return 0.0


def extract_attempts(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    attempts = result.get("attempts")
    if not isinstance(attempts, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for attempt in attempts:
        if isinstance(attempt, dict):
            normalized.append(attempt)
    return normalized


def build_provider_latency_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    attempts = extract_attempts(result)
    total_latency = sum(_safe_latency(a.get("latency_ms")) for a in attempts)
    failed_attempts = sum(1 for a in attempts if str(a.get("status", "")).lower() not in {"success", "partial", "mock"})
    provider_path = [a.get("provider") for a in attempts if a.get("provider")]

    return {
        "chain": result.get("chain"),
        "status": result.get("status"),
        "selected_provider": result.get("selected_provider"),
        "fallback_used": bool(result.get("fallback_used")),
        "attempt_count": len(attempts),
        "failed_attempt_count": failed_attempts,
        "total_latency_ms": round(total_latency, 2),
        "provider_path": provider_path,
        "attempts": attempts,
        "error": result.get("error"),
    }


def build_telemetry_row(
    *,
    user_id: int,
    request_id: str,
    mode: str,
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if mode != "adapter_chain":
        return None

    summary = build_provider_latency_summary(result)

    return {
        "user_id": user_id,
        "request_id": request_id,
        "mode": mode,
        "chain": summary.get("chain"),
        "status": summary.get("status"),
        "selected_provider": summary.get("selected_provider"),
        "fallback_used": summary.get("fallback_used", False),
        "attempt_count": summary.get("attempt_count", 0),
        "total_latency_ms": summary.get("total_latency_ms", 0.0),
        "error": summary.get("error"),
        "attempts_json": json.dumps(summary.get("attempts", []), ensure_ascii=False),
    }
