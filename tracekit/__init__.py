"""django-tracekit — Lightweight, production-safe Django APM."""

__version__ = "0.1.0"

default_app_config = "tracekit.apps.TracekitConfig"


def get_time_log():
    """Get the TimeLogger for the current request (or a no-op instance)."""
    from tracekit.middleware.request import get_current_request
    from tracekit.timelogger import TimeLogger

    request = get_current_request()
    if request and hasattr(request, "_tracekit_timelogger"):
        return request._tracekit_timelogger
    return TimeLogger()
