"""Root conftest — shared fixtures available to all test directories."""

import os
from collections.abc import Generator

# Must run before any onyx import. Parent conftest loads first and pulls
# app_configs, which freezes MCP_GATEWAY_ENABLED at import time.
os.environ.setdefault("MCP_GATEWAY_ENABLED", "true")
# litellm otherwise fetches its model cost map from the network at import
# time, so pricing lookups differ between runs (the remote map lags the
# bundled one). The bundled map keeps tests deterministic and offline.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import pytest

from onyx.llm.litellm_singleton.config import load_model_metadata_enrichments
from onyx.llm.model_capabilities import get_model_map
from onyx.llm.model_name_parser import parse_litellm_model_name


@pytest.fixture(scope="session", autouse=True)
def _load_model_enrichments_once() -> Generator[None, None, None]:
    """Enrich litellm's model metadata once per worker before any test runs.

    Tests read model metadata through a cached map; whichever test in a
    worker runs first decides whether the enriched data is visible. Loading
    here (instead of per-directory) and clearing the caches keeps those
    lookups deterministic under pytest-xdist.
    """
    load_model_metadata_enrichments()
    get_model_map.cache_clear()
    parse_litellm_model_name.cache_clear()
    yield
