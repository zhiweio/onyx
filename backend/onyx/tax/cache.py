import hashlib
import json
from typing import Any

from onyx.redis.redis_pool import get_redis_client
from onyx.tax.models import NormalizedRecord
from onyx.utils.logger import setup_logger

logger = setup_logger()

TAX_CACHE_PREFIX = "tax_live_query:"
TAX_CACHE_TTL_SECONDS = 6 * 60 * 60


def cache_key(source_id: str, query: str) -> str:
    digest = hashlib.sha256(f"{source_id}:{query}".encode()).hexdigest()[:24]
    return f"{TAX_CACHE_PREFIX}{source_id}:{digest}"


def get_cached_records(source_id: str, query: str) -> list[NormalizedRecord] | None:
    try:
        raw = get_redis_client().get(cache_key(source_id, query))
    except Exception:
        logger.debug("Tax live-query cache read failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return [NormalizedRecord.model_validate(item) for item in payload]
    except Exception:
        logger.debug("Tax live-query cache decode failed", exc_info=True)
        return None


def set_cached_records(
    source_id: str, query: str, records: list[NormalizedRecord]
) -> None:
    try:
        payload: list[dict[str, Any]] = [item.model_dump(mode="json") for item in records]
        get_redis_client().set(
            cache_key(source_id, query),
            json.dumps(payload, ensure_ascii=False),
            ex=TAX_CACHE_TTL_SECONDS,
        )
    except Exception:
        logger.debug("Tax live-query cache write failed", exc_info=True)
