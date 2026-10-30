"""
APILogMiddleware — request / response logging with CPU + RSS profiling.
"""

import json
import logging
import os
import resource
import threading
import time
import traceback

from django.utils import timezone

from tracekit.buffer import BufferManager
from tracekit.config import get_config
from tracekit.models import APILog
from tracekit.settings import get_setting
from tracekit.utils import get_client_ip, get_request_id, normalize_url, split_csv

logger = logging.getLogger("tracekit")


class APILogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.pod_ip = os.getenv("POD_IP", os.getenv("THIS_POD_IP", ""))
        self.process_id = os.getpid()

    def __call__(self, request):
        url = request.path
        health_path = get_setting("HEALTH_CHECK_PATH")
        if health_path and url == health_path:
            return self.get_response(request)

        start_time = time.perf_counter()
        body_data = self._capture_body(request)

        config = get_config(request)

        cpu_before = cpu_after = 0
        rss_before = rss_after = 0
        if config.cpu_profiling_enabled:
            usage = resource.getrusage(resource.RUSAGE_THREAD)
            cpu_before = usage.ru_utime + usage.ru_stime
            rss_before = usage.ru_maxrss

        response = self.get_response(request)

        if config.cpu_profiling_enabled:
            usage = resource.getrusage(resource.RUSAGE_THREAD)
            cpu_after = usage.ru_utime + usage.ru_stime
            rss_after = usage.ru_maxrss

        try:
            if not config.api_log_enabled:
                return response

            normalized = normalize_url(url)
            url_filter = split_csv(config.api_log_url_filter)
            if url_filter and normalized not in url_filter:
                return response

            user_id = self._get_user_id(request)
            if config.api_log_user_id and (
                    not user_id or user_id != config.api_log_user_id):
                return response

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            response_body = ""
            response_headers = ""
            capture_urls = split_csv(config.api_log_capture_response_url)
            if ((capture_urls and normalized in capture_urls) or (
                    user_id and
                    user_id == config.api_log_capture_response_user_id)):
                response_body = response.content.decode("utf-8", errors="replace")
                response_headers = dict(response.headers)

            now = timezone.now()
            BufferManager().get("api_log").add(APILog(
                request_id=get_request_id(request),
                user_id=user_id,
                method=request.method,
                url=normalized,
                full_url=request.build_absolute_uri(),
                request_ip=get_client_ip(request),
                request_headers=json.dumps(dict(request.headers)),
                request_body=body_data,
                response_code=response.status_code,
                response_headers=(json.dumps(response_headers) if response_headers else ""),
                response_body=response_body,
                response_time=duration_ms,
                cpu_time=(cpu_after - cpu_before) * 1000,
                rss_before=rss_before,
                rss_delta=rss_after - rss_before,
                pod_ip=self.pod_ip,
                process_id=self.process_id,
                thread_id=threading.get_ident(),
                created_at=now,
                created_at_ymd=now.date(),
            ))
        except Exception:
            logger.debug("tracekit APILog error", exc_info=True)

        return response


    @staticmethod
    def _capture_body(request) -> str:
        if request.method not in ("POST", "PUT", "PATCH"):
            return ""
        try:
            content_type = getattr(request, "content_type", "") or ""
            if "application/json" in content_type:
                if not hasattr(request, "_body"):
                    _ = request.body  # triggers read + cache
                return request.body.decode("utf-8", errors="replace")
            if request.POST:
                return json.dumps(request.POST.dict())
        except Exception:
            logger.debug("tracekit body capture error", exc_info=True)
        return ""

    @staticmethod
    def _get_user_id(request):
        if hasattr(request, "user") and request.user.is_authenticated:
            return request.user.id
        return None
