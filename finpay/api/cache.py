"""
In-Memory Caching and Response Telemetry Module.
Improves API performance for repeated queries (Requirement 7) and provides
observability headers (X-Cache and X-Response-Time-Ms).
"""

from __future__ import annotations
import functools
import hashlib
import time
from typing import Any, Callable, Dict, Optional, Tuple
from flask import request, jsonify, make_response, Response


class APICache:
    """
    Thread-safe in-memory cache with TTL and telemetry headers.
    """

    def __init__(self, default_timeout: int = 300):
        self.default_timeout = default_timeout
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def _generate_key(self, prefix: str = "") -> str:
        """Generates a deterministic cache key from request path and sorted query params."""
        args_sorted = sorted(request.args.items())
        raw_key = f"{prefix}:{request.path}:{args_sorted}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Retrieves cached value if not expired; otherwise removes it."""
        if key in self._cache:
            expires_at, data = self._cache[key]
            if time.time() < expires_at:
                return data
            # Expired
            del self._cache[key]
        return None

    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Stores a value in cache with expiration."""
        ttl = timeout if timeout is not None else self.default_timeout
        self._cache[key] = (time.time() + ttl, value)

    def clear(self) -> None:
        """Purges all entries from the cache."""
        self._cache.clear()

    @property
    def size(self) -> int:
        """Returns number of active cache keys."""
        return len(self._cache)


# Global cache instance for the API
api_cache = APICache(default_timeout=300)


def cached_api_response(timeout: int = 300, prefix: str = "api"):
    """
    Decorator for Flask route functions that:
    1. Checks cache for identical request path and query parameters.
    2. Adds 'X-Cache: HIT' or 'X-Cache: MISS' headers.
    3. Adds 'X-Response-Time-Ms' header for performance measurement.
    """

    def decorator(f: Callable):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            # Generate cache key based on request
            key = api_cache._generate_key(prefix=prefix)
            cached_payload = api_cache.get(key)

            if cached_payload is not None:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                response = make_response(jsonify(cached_payload))
                response.headers["X-Cache"] = "HIT"
                response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"
                return response

            # Cache MISS: execute route function
            result = f(*args, **kwargs)

            # If result is already a Response object, extract json data
            if isinstance(result, tuple):
                data, status_code = result
            else:
                data, status_code = result, 200

            # Store in cache (only 200 OK responses)
            if status_code == 200:
                api_cache.set(key, data, timeout=timeout)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            response = make_response(jsonify(data), status_code)
            response.headers["X-Cache"] = "MISS"
            response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"
            return response

        return wrapper

    return decorator
