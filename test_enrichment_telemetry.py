import json
import unittest

from enrichment_telemetry import (
    build_provider_latency_summary,
    build_telemetry_overview,
    build_telemetry_row,
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
            top_providers=[{"provider": "wikidata", "request_count": 6}],
        )

        self.assertEqual(overview["total_requests"], 10)
        self.assertEqual(overview["fallback_rate_pct"], 40.0)
        self.assertEqual(overview["success_rate_pct"], 90.0)
        self.assertEqual(overview["avg_attempt_count"], 1.7)
        self.assertEqual(overview["avg_latency_ms"], 142.46)
        self.assertEqual(overview["top_providers"][0]["provider"], "wikidata")

    def test_overview_handles_zero_requests(self):
        overview = build_telemetry_overview(
            total_requests=0,
            fallback_requests=0,
            successful_requests=0,
            avg_attempt_count=0,
            avg_latency_ms=0,
            top_providers=[],
        )

        self.assertEqual(overview["fallback_rate_pct"], 0.0)
        self.assertEqual(overview["success_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
