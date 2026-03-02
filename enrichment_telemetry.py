"""Telemetry helpers for enrichment adapter-chain rollout.

Keeps response tracing/persistence formatting separate from Flask route code so
logic can be unit-tested in isolation.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _safe_latency(value: Any) -> float:
    try:
        parsed = float(value)
        if parsed < 0:
            return 0.0
        return parsed
    except (TypeError, ValueError):
        return 0.0


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _parse_hour_bucket(value: Any) -> Optional[str]:
    if not value:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    normalized = raw.replace("Z", "+00:00")
    parsed: Optional[datetime] = None

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        ):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    hour = parsed.replace(minute=0, second=0, microsecond=0)
    return hour.isoformat().replace("+00:00", "Z")


def extract_attempts(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    attempts = result.get("attempts")
    if not isinstance(attempts, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for attempt in attempts:
        if isinstance(attempt, dict):
            normalized.append(attempt)
    return normalized


def compute_latency_p95_ms(latencies: List[Any]) -> float:
    values = sorted(_safe_latency(v) for v in latencies if _safe_latency(v) > 0)
    if not values:
        return 0.0

    # nearest-rank percentile (95th)
    idx = int(round(0.95 * (len(values) - 1)))
    idx = min(max(idx, 0), len(values) - 1)
    return round(float(values[idx]), 2)


def build_provider_error_breakdown(
    attempts_payloads: List[Any],
    *,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    errors = Counter()

    for payload in attempts_payloads:
        attempts: List[Dict[str, Any]] = []

        if isinstance(payload, list):
            attempts = [a for a in payload if isinstance(a, dict)]
        elif isinstance(payload, str):
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, list):
                    attempts = [a for a in parsed if isinstance(a, dict)]
            except (TypeError, ValueError, json.JSONDecodeError):
                attempts = []

        for attempt in attempts:
            status = str(attempt.get("status", "")).lower()
            if status in {"success", "partial", "mock"}:
                continue
            provider = str(attempt.get("provider") or "unknown").strip() or "unknown"
            errors[provider] += 1

    return [
        {"provider": provider, "error_count": int(count)}
        for provider, count in errors.most_common(max(1, int(top_n or 5)))
    ]


def build_hourly_trends(rows: List[Dict[str, Any]], *, max_points: int = 168) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        hour = _parse_hour_bucket(row.get("created_at"))
        if not hour:
            continue

        entry = buckets.setdefault(
            hour,
            {
                "total_requests": 0,
                "fallback_requests": 0,
                "error_requests": 0,
                "latencies": [],
            },
        )

        entry["total_requests"] += 1
        if _safe_bool(row.get("fallback_used")):
            entry["fallback_requests"] += 1

        status = str(row.get("status") or "").strip().lower()
        if status not in {"success", "partial", "mock"}:
            entry["error_requests"] += 1

        latency = _safe_latency(row.get("total_latency_ms"))
        if latency > 0:
            entry["latencies"].append(latency)

    ordered_hours = sorted(buckets.keys())
    if max_points > 0 and len(ordered_hours) > max_points:
        ordered_hours = ordered_hours[-max_points:]

    trends: List[Dict[str, Any]] = []
    for hour in ordered_hours:
        entry = buckets[hour]
        total_requests = int(entry["total_requests"])
        fallback_requests = int(entry["fallback_requests"])
        error_requests = int(entry["error_requests"])

        fallback_rate = round((fallback_requests / total_requests) * 100, 2) if total_requests else 0.0
        error_rate = round((error_requests / total_requests) * 100, 2) if total_requests else 0.0

        trends.append(
            {
                "hour": hour,
                "total_requests": total_requests,
                "fallback_rate_pct": fallback_rate,
                "error_rate_pct": error_rate,
                "latency_p95_ms": compute_latency_p95_ms(entry["latencies"]),
            }
        )

    return trends


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


def build_telemetry_overview(
    *,
    total_requests: int,
    fallback_requests: int,
    successful_requests: int,
    avg_attempt_count: float,
    avg_latency_ms: float,
    latency_p95_ms: float,
    top_providers: List[Dict[str, Any]],
    provider_error_breakdown: List[Dict[str, Any]],
    hourly_trends: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    total = max(int(total_requests or 0), 0)
    fallback_total = max(int(fallback_requests or 0), 0)
    successful_total = max(int(successful_requests or 0), 0)

    fallback_rate = round((fallback_total / total) * 100, 2) if total else 0.0
    success_rate = round((successful_total / total) * 100, 2) if total else 0.0

    return {
        "total_requests": total,
        "fallback_requests": fallback_total,
        "successful_requests": successful_total,
        "fallback_rate_pct": fallback_rate,
        "success_rate_pct": success_rate,
        "avg_attempt_count": round(float(avg_attempt_count or 0.0), 2),
        "avg_latency_ms": round(float(avg_latency_ms or 0.0), 2),
        "latency_p95_ms": round(float(latency_p95_ms or 0.0), 2),
        "top_providers": top_providers,
        "provider_error_breakdown": provider_error_breakdown,
        "hourly_trends": hourly_trends or [],
    }
