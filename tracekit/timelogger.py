"""
TimeLogger — per-step CPU / wall-clock / RSS instrumentation.

Usage inside a view or service function:

    from tracekit import get_time_log

    tl = get_time_log()
    tl.log("after serializer")
    ...heavy work...
    tl.log("after heavy work")

Checkpoints are bulk-written to the database at the end of the request
by TimingMiddleware.
"""

import inspect
import resource
import sys
import time

from tracekit.models import RequestTimeLog
from tracekit.utils import normalize_url


class TimeLogger:
    """
    Collects per-step timing checkpoints during a single request.

    When instantiated without a *url*, all ``log()`` calls are no-ops
    so that code outside a request context (management commands, Celery
    tasks) doesn't break.
    """

    def __init__(self, url=None, min_time=10, enable_query_log=False):
        self.url = url
        self.normalized_url = normalize_url(url) if url else None
        self.start_time = time.perf_counter()
        self.last_time = self.start_time
        self.min_time = min_time  # ms
        self.enable_query_log = enable_query_log
        self._logs: list[RequestTimeLog] = []

        # CPU / RSS baseline
        usage = resource.getrusage(resource.RUSAGE_THREAD)
        self.cpu_start = usage.ru_utime + usage.ru_stime
        self.cpu_last = self.cpu_start
        self.rss_last = usage.ru_maxrss

        self._is_shell = any(
            arg in sys.argv for arg in ("shell", "shell_plus"))

    # ------------------------------------------------------------------
    def log(self, message: str = ""):
        """Record a timing checkpoint. Skips if below *min_time*."""
        if not self.url:
            return

        try:
            now = time.perf_counter()
            delta_step = (now - self.last_time) * 1000  # ms

            if delta_step < self.min_time:
                return

            delta_total = (now - self.start_time) * 1000

            usage = resource.getrusage(resource.RUSAGE_THREAD)
            cpu_now = usage.ru_utime + usage.ru_stime
            cpu_delta_total = (cpu_now - self.cpu_start) * 1000
            cpu_delta_step = (cpu_now - self.cpu_last) * 1000
            rss_delta_step = usage.ru_maxrss - self.rss_last
            self.last_time = now
            self.cpu_last = cpu_now
            self.rss_last = usage.ru_maxrss
            frame = inspect.currentframe().f_back
            func_name = frame.f_code.co_name
            filename = frame.f_code.co_filename
            line_no = frame.f_lineno

            self._logs.append(RequestTimeLog(
                url=self.url,
                normalized_url=self.normalized_url,
                message=message or "",
                func=func_name,
                filename=filename,
                line=line_no,
                since_start=round(delta_total, 3),
                since_last=round(delta_step, 3),
                cpu_since_start=round(cpu_delta_total, 3),
                cpu_since_last=round(cpu_delta_step, 3),
                rss_delta=rss_delta_step,
            ))

            if self._is_shell:
                print(
                    f"[tracekit] {message or ''} — "
                    f"{func_name} in {filename}:{line_no} "
                    f"took {round(delta_step, 3)}ms"
                )

            if self.enable_query_log:
                self._emit_query_marker(
                    message, func_name, filename, line_no,
                    delta_step, cpu_delta_step,
                )
        except Exception as exc:
            # Never break the request for a logging failure.
            if self._is_shell:
                print(f"[tracekit] log error: {exc}")

    # ------------------------------------------------------------------
    def save(self, user_id, request_id):
        """Bulk-write collected checkpoints to the database."""
        if not self.url or not self._logs:
            return
        try:
            for entry in self._logs:
                entry.user_id = user_id
                entry.request_id = request_id
            RequestTimeLog.objects.bulk_create(self._logs)
        except Exception as exc:
            if self._is_shell:
                print(f"[tracekit] save error: {exc}")

    # ------------------------------------------------------------------
    def _emit_query_marker(
        self, message, func_name, filename, line_no,
        delta_step, cpu_delta_step,
    ):
        """
        Execute a dummy SELECT so the checkpoint shows up in the SQL
        query log alongside the real queries it's interleaved with.
        """
        from django.db import connections
        from tracekit.settings import get_setting

        try:
            marker = (
                f"{message or ''}-{func_name} in {filename}:{line_no} "
                f"took {round(delta_step, 3)}ms "
                f"cpu {round(cpu_delta_step, 3)}ms"
            )
            conn = connections[get_setting("DB_ALIAS")]
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT %s", [marker])
                cursor.fetchone()
            finally:
                cursor.close()
        except Exception:
            pass
