"""
Default settings for django-tracekit.

Override any of these in your Django settings under the TRACEKIT dict:

    TRACEKIT = {
        "REQUEST_ID_HEADER": "HTTP_X_REQUEST_ID",
        "HEALTH_CHECK_PATH": "/-/healthz/",
        ...
    }
"""

from django.conf import settings

DEFAULTS = {
    # Header to extract request ID from (META key format).
    # If absent, a UUID is generated per request.
    "REQUEST_ID_HEADER": "HTTP_X_REQUEST_ID",

    # Path to skip entirely (health checks).
    "HEALTH_CHECK_PATH": "/-/healthz/",

    # Database alias for query capture.
    "DB_ALIAS": "default",

    # Cache key and timeout for the runtime config singleton.
    "CONFIG_CACHE_KEY": "tracekit:config",
    "CONFIG_CACHE_TIMEOUT": 300,  # seconds
    "CONFIG_CACHE_ALIAS": "default",
}


def get_setting(key):
    user_settings = getattr(settings, "TRACEKIT", {})
    return user_settings.get(key, DEFAULTS[key])
