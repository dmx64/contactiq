"""
Provider adapter scaffolding for ContactIQ alternative architecture.

Goal:
- decouple provider execution from route/business logic
- add deterministic fallback chains
- collect per-provider latency/error telemetry for migration decisions
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Dict, List, Optional, Sequence


LOG = logging.getLogger(__name__)


@dataclass
class ProviderAttempt:
    provider: str
    status: str
    latency_ms: float
    error: Optional[str]
    fallback: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
            "fallback": self.fallback,
        }


class ProviderAdapter:
    """Minimal provider adapter contract."""

    name: str = "unknown"

    def fetch(self, contact: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError


class ProviderFallbackChain:
    """
    Runs adapters in order and stops at the first usable result.

    Usable result = status in {success, partial, mock} and data/items payload exists.
    """

    def __init__(self, chain_name: str, adapters: Sequence[ProviderAdapter], logger: Optional[logging.Logger] = None):
        if not adapters:
            raise ValueError("ProviderFallbackChain requires at least one adapter")

        self.chain_name = chain_name
        self.adapters = list(adapters)
        self.logger = logger or LOG

    def run(self, contact: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        attempts: List[ProviderAttempt] = []
        cfg = config or {}

        for index, adapter in enumerate(self.adapters):
            started = time.perf_counter()
            result: Dict[str, Any]

            try:
                raw = adapter.fetch(contact, cfg)
                result = raw if isinstance(raw, dict) else {
                    "status": "error",
                    "error": "Provider returned non-dict payload",
                }
            except Exception as exc:  # defensive boundary around external APIs/SDKs
                result = {
                    "status": "error",
                    "error": str(exc),
                }

            latency_ms = (time.perf_counter() - started) * 1000
            status = str(result.get("status", "unknown"))
            error = str(result.get("error")) if result.get("error") is not None else None

            attempt = ProviderAttempt(
                provider=adapter.name,
                status=status,
                latency_ms=latency_ms,
                error=error,
                fallback=index > 0,
            )
            attempts.append(attempt)

            self.logger.info(
                "provider_chain_attempt",
                extra={
                    "chain": self.chain_name,
                    "provider": adapter.name,
                    "status": status,
                    "latency_ms": round(latency_ms, 2),
                    "fallback": index > 0,
                },
            )

            if self._is_usable_result(result):
                return {
                    "status": "success",
                    "chain": self.chain_name,
                    "selected_provider": adapter.name,
                    "fallback_used": index > 0,
                    "attempts": [a.to_dict() for a in attempts],
                    "result": result,
                }

        return {
            "status": "failed",
            "chain": self.chain_name,
            "selected_provider": None,
            "fallback_used": len(attempts) > 1,
            "attempts": [a.to_dict() for a in attempts],
            "error": attempts[-1].error if attempts else "No providers executed",
        }

    @staticmethod
    def _is_usable_result(result: Dict[str, Any]) -> bool:
        status = str(result.get("status", "")).lower()
        if status not in {"success", "partial", "mock"}:
            return False

        payload = result.get("data")
        if payload:
            return True

        items = result.get("items")
        return isinstance(items, list) and len(items) > 0


class GitHubPersonAdapter(ProviderAdapter):
    name = "github"

    def fetch(self, contact: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from providers import GitHubAPI

        cfg = config or {}
        token = cfg.get("github_token")
        email = contact.get("email")
        full_name = contact.get("full_name")

        if email:
            return GitHubAPI.enrich_by_email(email, token)
        if full_name:
            return GitHubAPI.search_user(full_name, token)

        return {"status": "error", "error": "full_name or email is required"}


class WikidataPersonAdapter(ProviderAdapter):
    name = "wikidata"

    def fetch(self, contact: Dict[str, Any], _config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from providers import WikidataAPI

        full_name = contact.get("full_name")
        if not full_name:
            return {"status": "error", "error": "full_name is required"}

        return WikidataAPI.search_person(full_name)


def build_person_enrichment_chain() -> ProviderFallbackChain:
    """
    Initial vertical slice chain:
    1) GitHub (great for tech personas)
    2) Wikidata (broad public-figure fallback)
    """

    return ProviderFallbackChain(
        chain_name="person_enrichment",
        adapters=[GitHubPersonAdapter(), WikidataPersonAdapter()],
    )


def enrich_person_with_fallback(contact: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    chain = build_person_enrichment_chain()
    return chain.run(contact=contact, config=config)
