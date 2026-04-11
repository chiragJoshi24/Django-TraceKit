"""
TimingMiddleware — attaches a TimeLogger to the request and persists
collected checkpoints at the end of the response cycle.
"""

import random
import re

from django.utils import timezone as tz_utils
from django.utils.deprecation import MiddlewareMixin

from tracekit.config import get_config
from tracekit.middleware.query_log import is_query_log_enabled
from tracekit.timelogger import TimeLogger
from tracekit.utils import get_request_id, normalize_url


class TimingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        config = get_config(request)
        normalized = normalize_url(request.path)

        if not _should_enable(config, normalized):
            return

        threshold = config.time_log_threshold
        if random.random() > threshold:
            return

        enable_query_log = is_query_log_enabled(request, config)
        request._tracekit_timelogger = TimeLogger(
            url=request.path,
            min_time=config.time_log_min_time,
            enable_query_log=enable_query_log,
        )

    def process_response(self, request, response):
        tl = getattr(request, "_tracekit_timelogger", None)
        if tl is not None:
            user_id = None
            if hasattr(request, "user") and request.user.is_authenticated:
                user_id = request.user.id
            tl.save(user_id, get_request_id(request))
        return response


def _should_enable(config, normalized_url: str) -> bool:
    if not config.time_log_url:
        return False
    if config.time_log_url != normalized_url:
        return False

    # Time-window check (optional)
    if config.time_log_start and config.time_log_end:
        now = tz_utils.localtime().time()
        return config.time_log_start <= now <= config.time_log_end

    # No time window configured → always on for matching URL
    return True
