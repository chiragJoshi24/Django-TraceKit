"""
APIQueryLogMiddleware — per-request SQL query capture.
"""

import logging
from urllib.parse import urlparse

from django.db import connections
from django.test.utils import CaptureQueriesContext

from tracekit.config import get_config
from tracekit.models import APIQueryLog
from tracekit.settings import get_setting
from tracekit.utils import get_request_id, normalize_url, split_csv

logger = logging.getLogger("tracekit")


class APIQueryLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        config = get_config(request)

        if not is_query_log_enabled(request, config):
            return self.get_response(request)

        url = request.path
        normalized = normalize_url(url)
        db_alias = get_setting("DB_ALIAS")

        with CaptureQueriesContext(connections[db_alias]) as ctx:
            response = self.get_response(request)

        try:
            user_id = None
            if hasattr(request, "user") and request.user.is_authenticated:
                user_id = request.user.id

            logs = [
                APIQueryLog(
                    request_id=get_request_id(request),
                    url=url,
                    normalized_url=normalized,
                    query=q["sql"],
                    query_time=float(q["time"]),
                    user_id=user_id,
                )
                for q in ctx.captured_queries
                if isinstance(q, dict)
            ]
            if logs:
                APIQueryLog.objects.bulk_create(logs)
        except Exception:
            logger.debug("tracekit APIQueryLog error", exc_info=True)

        return response


def is_query_log_enabled(request, config=None) -> bool:
    """Check runtime config to decide if query logging should fire."""
    if config is None:
        config = get_config(request)

    if not config.query_log_enabled or not config.query_log_url_filter:
        return False

    url = request.path
    normalized = normalize_url(url)

    url_filter = split_csv(config.query_log_url_filter)
    if url_filter and normalized not in url_filter:
        return False

    if config.query_log_user_id:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if user.id != config.query_log_user_id:
            return False

    # Domain whitelist
    allowed = split_csv(config.query_log_allowed_domains)
    if allowed:
        full_url = request.build_absolute_uri()
        domain = urlparse(full_url).netloc
        if domain not in allowed:
            return False

    return True
