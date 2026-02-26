import unittest

from provider_adapters import ProviderAdapter, ProviderFallbackChain


class FakeAdapter(ProviderAdapter):
    def __init__(self, name, response=None, exception=None):
        self.name = name
        self._response = response
        self._exception = exception

    def fetch(self, contact, config=None):
        if self._exception:
            raise self._exception
        return self._response


class ProviderFallbackChainTests(unittest.TestCase):
    def test_primary_success_short_circuits(self):
        chain = ProviderFallbackChain(
            chain_name="test_chain",
            adapters=[
                FakeAdapter("primary", {"status": "success", "data": {"x": 1}}),
                FakeAdapter("secondary", {"status": "success", "data": {"x": 2}}),
            ],
        )

        result = chain.run(contact={"full_name": "Ada Lovelace"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_provider"], "primary")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(len(result["attempts"]), 1)

    def test_fallback_on_error(self):
        chain = ProviderFallbackChain(
            chain_name="test_chain",
            adapters=[
                FakeAdapter("primary", {"status": "error", "error": "timeout"}),
                FakeAdapter("secondary", {"status": "success", "data": {"ok": True}}),
            ],
        )

        result = chain.run(contact={"full_name": "Grace Hopper"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_provider"], "secondary")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["attempts"][0]["status"], "error")

    def test_fail_when_all_providers_fail(self):
        chain = ProviderFallbackChain(
            chain_name="test_chain",
            adapters=[
                FakeAdapter("primary", {"status": "error", "error": "timeout"}),
                FakeAdapter("secondary", exception=RuntimeError("boom")),
            ],
        )

        result = chain.run(contact={"full_name": "Unknown"})

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["selected_provider"])
        self.assertEqual(len(result["attempts"]), 2)
        self.assertIn("boom", result["error"])


if __name__ == "__main__":
    unittest.main()
