"""
Runtime configuration loader with per-request + cache-framework caching.

Cache layers (fastest → slowest):
    1. request attribute  (_tracekit_config)
    2. Django cache framework  (configurable alias)
    3. Database  (RuntimeConfig singleton)
"""

import logging

from tracekit.settings import get_setting

logger = logging.getLogger("tracekit")

_SENTINEL = object()


def get_config(request=None):
    """
    Return the current RuntimeConfig instance, cached at three layers.
    """
    # Layer 1: per-request memoization
    if request and hasattr(request, "_tracekit_config"):
        return request._tracekit_config

    # Layer 2: Django cache framework
    from django.core.cache import caches

    cache_alias = get_setting("CONFIG_CACHE_ALIAS")
    cache_key = get_setting("CONFIG_CACHE_KEY")
    cache_timeout = get_setting("CONFIG_CACHE_TIMEOUT")

    try:
        cache = caches[cache_alias]
        cached = cache.get(cache_key, _SENTINEL)
    except Exception:
        cached = _SENTINEL

    if cached is not _SENTINEL and cached is not None:
        config = cached
    else:
        # Layer 3: database
        from tracekit.models import RuntimeConfig
        config = RuntimeConfig.load()
        try:
            cache.set(cache_key, config, cache_timeout)
        except Exception:
            logger.debug("tracekit: failed to write config to cache")

    # Pin to request for the rest of this cycle
    if request:
        request._tracekit_config = config

    return config


def invalidate_config_cache():
    """Clear the cached RuntimeConfig. Call after saving config changes."""
    from django.core.cache import caches

    cache_alias = get_setting("CONFIG_CACHE_ALIAS")
    cache_key = get_setting("CONFIG_CACHE_KEY")
    try:
        caches[cache_alias].delete(cache_key)
    except Exception:
        pass
