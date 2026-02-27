"""Routing helpers for person enrichment mode selection.

This module keeps feature-flag logic isolated so it can be tested without
booting the Flask app.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from provider_adapters import enrich_person_with_fallback

ENABLED_VALUES = {"1", "true", "yes", "on"}


def adapter_chain_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    source = env or os.environ
    value = source.get("CONTACTIQ_ENABLE_ADAPTER_CHAIN", "false")
    return str(value).strip().lower() in ENABLED_VALUES


def provider_runtime_config(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    source = env or os.environ
    return {
        "github_token": source.get("GITHUB_TOKEN"),
        "gnews_key": source.get("GNEWS_API_KEY"),
        "guardian_key": source.get("GUARDIAN_API_KEY"),
        "opencorporates_key": source.get("OPENCORPORATES_API_KEY"),
        "opensanctions_url": source.get("OPENSANCTIONS_URL"),
        "opensanctions_key": source.get("OPENSANCTIONS_API_KEY"),
    }


def enrich_person(
    contact: Dict[str, Any],
    *,
    force_adapter_chain: Optional[bool] = None,
    pipeline: Optional[Any] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    use_adapter_chain = force_adapter_chain if force_adapter_chain is not None else adapter_chain_enabled(env)

    if use_adapter_chain:
        return {
            "mode": "adapter_chain",
            "result": enrich_person_with_fallback(contact, config=provider_runtime_config(env)),
        }

    if pipeline is None:
        from providers import EnrichmentPipeline  # lazy import keeps tests lightweight

        pipeline = EnrichmentPipeline(config=provider_runtime_config(env))

    active_pipeline = pipeline
    return {
        "mode": "legacy_pipeline",
        "result": active_pipeline.enrich_contact(contact),
    }
