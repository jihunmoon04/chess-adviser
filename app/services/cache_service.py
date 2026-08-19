import time
import json
import logging
from typing import Optional, Dict, Any, Tuple, List

from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Manages caching with Redis and graceful in-memory fallback."""

    def __init__(self):
        self._redis_client = None
        self._memory_cache: Dict[str, Tuple[float, str]] = {}  # key -> (expiry_timestamp, json_data)
        self._is_redis_ready = False

    async def initialize(self):
        """Initialize Redis connection if available."""
        if not settings.REDIS_URL:
            logger.info("No REDIS_URL configured. Using In-Memory cache.")
            return

        try:
            import redis.asyncio as aioredis
            self._redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=1.0,
            )
            # Test connection
            await self._redis_client.ping()
            self._is_redis_ready = True
            logger.info(f"Connected to Redis cache at {settings.REDIS_URL}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis ({e}). Falling back to In-Memory cache.")
            self._is_redis_ready = False
            self._redis_client = None

    async def close(self):
        if self._redis_client:
            await self._redis_client.close()

    def _make_key(self, before_fen: str, move_san: str, history_san: Optional[List[str]] = None) -> str:
        hist_str = "_".join(history_san) if history_san else ""
        return f"chess_adv_v9:{before_fen}:{move_san}:{hist_str}"

    async def get(self, before_fen: str, move_san: str, history_san: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        key = self._make_key(before_fen, move_san, history_san)

        if self._is_redis_ready and self._redis_client:
            try:
                cached_val = await self._redis_client.get(key)
                if cached_val:
                    return json.loads(cached_val)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")

        # In-memory fallback
        if key in self._memory_cache:
            expiry, json_str = self._memory_cache[key]
            if time.time() < expiry:
                return json.loads(json_str)
            else:
                del self._memory_cache[key]

        return None

    async def set(
        self,
        before_fen: str,
        move_san: str,
        data: Dict[str, Any],
        ttl_seconds: int = settings.CACHE_TTL_SECONDS,
        history_san: Optional[List[str]] = None,
    ):
        key = self._make_key(before_fen, move_san, history_san)
        ttl = ttl_seconds or settings.CACHE_TTL_SECONDS
        json_data = json.dumps(data)

        if self._is_redis_ready and self._redis_client:
            try:
                await self._redis_client.set(key, json_data, ex=ttl)
                return
            except Exception as e:
                logger.warning(f"Redis set error: {e}")

        # In-Memory fallback
        self._memory_cache[key] = (time.time() + ttl, json_data)


cache_service = CacheService()
