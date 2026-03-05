import json
import unittest

from enrichment_telemetry import (
    build_hourly_trend_alerts,
    build_hourly_trends,
    build_provider_error_breakdown,
    build_provider_latency_summary,
    build_telemetry_overview,
    build_telemetry_row,
    compute_latency_p95_ms,
    resolve_trend_alert_config,
)


class EnrichmentTelemetryTests(unittest.TestCase):
    def test_summary_aggregates_attempts(self):
        result = {
            "chain": "person_enrichment",
            "status": "success",
            "selected_provider": "wikidata",
            "fallback_used": True,
            "attempts": [
                {"provider": "github", "status": "error", "latency_ms": 120.5},
                {"provider": "wikidata", "status": "success", "latency_ms": 40.25},
            ],
        }

        summary = build_provider_latency_summary(result)

        self.assertEqual(summary["attempt_count"], 2)
        self.assertEqual(summary["failed_attempt_count"], 1)
        self.assertEqual(summary["provider_path"], ["github", "wikidata"])
        self.assertEqual(summary["total_latency_ms"], 160.75)

    def test_row_not_created_for_legacy_mode(self):
        row = build_telemetry_row(
            user_id=7,
            request_id="enr_abc",
            mode="legacy_pipeline",
            result={"status": "completed"},
        )
        self.assertIsNone(row)

    def test_row_created_for_adapter_mode(self):
        row = build_telemetry_row(
            user_id=7,
            request_id="enr_abc",
            mode="adapter_chain",
            result={
                "chain": "person_enrichment",
                "status": "failed",
                "selected_provider": None,
                "fallback_used": True,
                "attempts": [
                    {"provider": "github", "status": "error", "latency_ms": "22"},
                    {"provider": "wikidata", "status": "error", "latency_ms": 30},
                ],
                "error": "all providers failed",
            },
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["attempt_count"], 2)
        self.assertEqual(row["total_latency_ms"], 52.0)
        attempts = json.loads(row["attempts_json"])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(row["status"], "failed")

    def test_overview_computes_rates(self):
        overview = build_telemetry_overview(
            total_requests=10,
            fallback_requests=4,
            successful_requests=9,
            avg_attempt_count=1.7,
            avg_latency_ms=142.456,
            latency_p95_ms=300.5,
            top_providers=[{"provider": "wikidata", "request_count": 6}],
            provider_error_breakdown=[{"provider": "github", "error_count": 3}],
        )

        self.assertEqual(overview["total_requests"], 10)
        self.assertEqual(overview["fallback_rate_pct"], 40.0)
        self.assertEqual(overview["success_rate_pct"], 90.0)
        self.assertEqual(overview["avg_attempt_count"], 1.7)
        self.assertEqual(overview["avg_latency_ms"], 142.46)
        self.assertEqual(overview["latency_p95_ms"], 300.5)
        self.assertEqual(overview["top_providers"][0]["provider"], "wikidata")
        self.assertEqual(overview["provider_error_breakdown"][0]["provider"], "github")
        self.assertEqual(overview["hourly_trends"], [])
        self.assertEqual(overview["trend_alerts"], [])

    def test_overview_handles_zero_requests(self):
        overview = build_telemetry_overview(
            total_requests=0,
            fallback_requests=0,
            successful_requests=0,
            avg_attempt_count=0,
            avg_latency_ms=0,
            latency_p95_ms=0,
            top_providers=[],
            provider_error_breakdown=[],
        )

        self.assertEqual(overview["fallback_rate_pct"], 0.0)
        self.assertEqual(overview["success_rate_pct"], 0.0)

    def test_latency_p95(self):
        self.assertEqual(compute_latency_p95_ms([5, 10, 20, 100, 200]), 200.0)
        self.assertEqual(compute_latency_p95_ms([]), 0.0)

    def test_provider_error_breakdown(self):
        breakdown = build_provider_error_breakdown([
            json.dumps([
                {"provider": "github", "status": "error"},
                {"provider": "wikidata", "status": "success"},
            ]),
            [
                {"provider": "github", "status": "timeout"},
                {"provider": "google", "status": "error"},
            ],
        ])

        self.assertEqual(breakdown[0]["provider"], "github")
        self.assertEqual(breakdown[0]["error_count"], 2)

    def test_hourly_trends_aggregates_fallback_error_and_p95(self):
        trends = build_hourly_trends([
            {
                "created_at": "2026-03-02 06:10:00",
                "status": "success",
                "fallback_used": 0,
                "total_latency_ms": 120,
            },
            {
                "created_at": "2026-03-02 06:40:00",
                "status": "failed",
                "fallback_used": 1,
                "total_latency_ms": 300,
            },
            {
                "created_at": "2026-03-02 07:15:00",
                "status": "partial",
                "fallback_used": 1,
                "total_latency_ms": 80,
            },
            {
                "created_at": "2026-03-02T07:35:00Z",
                "status": "error",
                "fallback_used": "true",
                "total_latency_ms": 200,
            },
        ])

        self.assertEqual(len(trends), 2)

        first = trends[0]
        self.assertEqual(first["hour"], "2026-03-02T06:00:00Z")
        self.assertEqual(first["total_requests"], 2)
        self.assertEqual(first["fallback_rate_pct"], 50.0)
        self.assertEqual(first["error_rate_pct"], 50.0)
        self.assertEqual(first["latency_p95_ms"], 300.0)

        second = trends[1]
        self.assertEqual(second["hour"], "2026-03-02T07:00:00Z")
        self.assertEqual(second["total_requests"], 2)
        self.assertEqual(second["fallback_rate_pct"], 100.0)
        self.assertEqual(second["error_rate_pct"], 50.0)
        self.assertEqual(second["latency_p95_ms"], 200.0)

    def test_hourly_trend_alerts_detect_spike_and_regression(self):
        trends = [
            {"hour": "2026-03-02T00:00:00Z", "fallback_rate_pct": 5.0, "error_rate_pct": 2.0, "latency_p95_ms": 100.0},
            {"hour": "2026-03-02T01:00:00Z", "fallback_rate_pct": 8.0, "error_rate_pct": 3.0, "latency_p95_ms": 110.0},
            {"hour": "2026-03-02T02:00:00Z", "fallback_rate_pct": 10.0, "error_rate_pct": 4.0, "latency_p95_ms": 120.0},
            {"hour": "2026-03-02T03:00:00Z", "fallback_rate_pct": 45.0, "error_rate_pct": 30.0, "latency_p95_ms": 320.0},
        ]

        alerts = build_hourly_trend_alerts(trends, baseline_window=3, min_baseline_points=3)
        alert_types = {alert["type"] for alert in alerts}

        self.assertIn("fallback_spike", alert_types)
        self.assertIn("error_spike", alert_types)
        self.assertIn("latency_p95_regression", alert_types)


    def test_resolve_trend_alert_config_defaults(self):
        resolved = resolve_trend_alert_config()

        self.assertEqual(resolved["config"]["baseline_window"], 6)
        self.assertEqual(resolved["config"]["min_baseline_points"], 3)
        self.assertEqual(resolved["applied"]["env"], [])
        self.assertEqual(resolved["applied"]["query"], [])

    def test_resolve_trend_alert_config_env_and_query_precedence(self):
        resolved = resolve_trend_alert_config(
            query_params={"trend_baseline_window": "9", "trend_error_spike_delta_pct": "22.5"},
            env={
                "CONTACTIQ_TREND_BASELINE_WINDOW": "7",
                "CONTACTIQ_TREND_FALLBACK_SPIKE_DELTA_PCT": "25",
            },
        )

        self.assertEqual(resolved["config"]["baseline_window"], 9)
        self.assertEqual(resolved["config"]["fallback_spike_delta_pct"], 25.0)
        self.assertEqual(resolved["config"]["error_spike_delta_pct"], 22.5)
        self.assertIn("CONTACTIQ_TREND_BASELINE_WINDOW", resolved["applied"]["env"])
        self.assertIn("trend_baseline_window", resolved["applied"]["query"])

    def test_resolve_trend_alert_config_rejects_invalid_query(self):
        with self.assertRaises(ValueError):
            resolve_trend_alert_config(query_params={"trend_latency_regression_multiplier": "zero"})

        with self.assertRaises(ValueError):
            resolve_trend_alert_config(
                query_params={
                    "trend_baseline_window": "2",
                    "trend_min_baseline_points": "3",
                }
            )

    def test_resolve_trend_alert_config_chain_preset_from_env(self):
        resolved = resolve_trend_alert_config(
            chain="person_enrichment",
            env={
                "CONTACTIQ_TREND_CHAIN_PRESETS_JSON": json.dumps(
                    {
                        "person_enrichment": {
                            "fallback_spike_delta_pct": 12,
                            "error_spike_delta_pct": 8,
                            "baseline_window": 4,
                        }
                    }
                )
            },
        )

        self.assertEqual(resolved["config"]["fallback_spike_delta_pct"], 12.0)
        self.assertEqual(resolved["config"]["error_spike_delta_pct"], 8.0)
        self.assertEqual(resolved["config"]["baseline_window"], 4)
        self.assertEqual(resolved["applied"]["preset"]["name"], "person_enrichment")

    def test_resolve_trend_alert_config_query_preset_overrides_chain(self):
        env = {
            "CONTACTIQ_TREND_CHAIN_PRESETS_JSON": json.dumps(
                {
                    "person_enrichment": {"fallback_spike_delta_pct": 12},
                    "strict_rollout": {"fallback_spike_delta_pct": 6},
                }
            )
        }

        resolved = resolve_trend_alert_config(
            chain="person_enrichment",
            query_params={"trend_preset": "strict_rollout"},
            env=env,
        )

        self.assertEqual(resolved["config"]["fallback_spike_delta_pct"], 6.0)
        self.assertEqual(resolved["applied"]["preset"]["name"], "strict_rollout")

    def test_resolve_trend_alert_config_rejects_missing_explicit_preset(self):
        with self.assertRaises(ValueError):
            resolve_trend_alert_config(
                query_params={"trend_preset": "missing_profile"},
                env={"CONTACTIQ_TREND_CHAIN_PRESETS_JSON": "{}"},
            )


if __name__ == "__main__":
    unittest.main()
