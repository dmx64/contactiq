import os
import unittest
from unittest.mock import patch

from enrichment_router import adapter_chain_enabled, enrich_person


class FakePipeline:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def enrich_contact(self, contact):
        self.calls.append(contact)
        return self.payload


class EnrichmentRouterTests(unittest.TestCase):
    def test_adapter_chain_flag_enabled(self):
        with patch.dict(os.environ, {"CONTACTIQ_ENABLE_ADAPTER_CHAIN": "true"}, clear=False):
            self.assertTrue(adapter_chain_enabled())

    def test_legacy_pipeline_used_when_flag_disabled(self):
        pipeline = FakePipeline(payload={"status": "completed", "provider_count": 7})
        with patch.dict(os.environ, {"CONTACTIQ_ENABLE_ADAPTER_CHAIN": "false"}, clear=False):
            result = enrich_person({"full_name": "Ada Lovelace"}, pipeline=pipeline)

        self.assertEqual(result["mode"], "legacy_pipeline")
        self.assertEqual(result["result"]["status"], "completed")
        self.assertEqual(len(pipeline.calls), 1)

    def test_force_adapter_chain_overrides_flag(self):
        pipeline = FakePipeline(payload={"status": "completed"})

        with patch("enrichment_router.enrich_person_with_fallback", return_value={"status": "success", "chain": "person_enrichment"}) as mocked:
            with patch.dict(os.environ, {"CONTACTIQ_ENABLE_ADAPTER_CHAIN": "false"}, clear=False):
                result = enrich_person(
                    {"full_name": "Grace Hopper", "email": "grace@example.com"},
                    force_adapter_chain=True,
                    pipeline=pipeline,
                )

        self.assertEqual(result["mode"], "adapter_chain")
        self.assertEqual(result["result"]["status"], "success")
        self.assertEqual(len(pipeline.calls), 0)
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
