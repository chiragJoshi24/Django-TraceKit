import uuid
from django.db import models
from django.utils import timezone


class RuntimeConfig(models.Model):
    api_log_enabled = models.BooleanField(
        default=False, help_text="Master toggle for request/response logging."
    )
    api_log_url_filter = models.CharField(
        max_length=500, blank=True, default=""
    )
    api_log_user_id = models.IntegerField(
        default=0,
        help_text="Only log requests from this user ID. 0 = all users."
    )
    api_log_capture_response_url = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Comma-separated URLs for which to capture response body."
    )
    api_log_capture_response_user_id = models.PositiveIntegerField(
        default=0,
        help_text="Capture response body for this user ID. 0 = disabled."
    )
    cpu_profiling_enabled = models.BooleanField(
        default=True,
        help_text="Capture CPU time and RSS memory in API logs."
    )
    query_log_enabled = models.BooleanField(
        default=False,
        help_text="Master toggle for SQL query logging."
    )
    query_log_url_filter = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Comma-separated normalized URLs to capture queries for."
    )
    query_log_user_id = models.IntegerField(
        default=0,
        help_text="Only log queries for this user ID. 0 = all users."
    )
    query_log_allowed_domains = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Comma-separated allowed domains. Empty = all domains."
    )
    time_log_url = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Normalized URL to instrument with TimeLogger."
    )
    time_log_threshold = models.FloatField(
        default=1.0,
        help_text="Sampling rate: 0.0 (off) to 1.0 (every request)."
    )
    time_log_min_time = models.IntegerField(
        default=10,
        help_text="Minimum step duration (ms) to record a checkpoint."
    )
    time_log_start = models.TimeField(
        null=True, blank=True,
        help_text="Time-window start (server-local time). Both start and end must be set for the window to be active."
    )
    time_log_end = models.TimeField(
        null=True, blank=True,
        help_text="Time-window end (server-local time)."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tracekit runtime config"
        verbose_name_plural = "Tracekit runtime config"

    def __str__(self):
        return "Tracekit Runtime Config"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class APILog(models.Model):
    request_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    method = models.CharField(max_length=10)
    url = models.CharField(max_length=500, db_index=True)
    full_url = models.CharField(max_length=500)
    request_ip = models.CharField(max_length=50, db_index=True)
    request_headers = models.TextField(blank=True, default="")
    request_body = models.TextField(blank=True, default="")
    response_code = models.PositiveIntegerField()
    response_headers = models.TextField(blank=True, default="")
    response_body = models.TextField(blank=True, default="")
    response_time = models.FloatField(
        db_index=True, help_text="Response time in milliseconds.")
    cpu_time = models.FloatField(
        null=True, blank=True, help_text="CPU time in milliseconds.")
    rss_before = models.IntegerField(
        null=True, blank=True, help_text="RSS (KB) before request.")
    rss_delta = models.IntegerField(
        null=True, blank=True, help_text="RSS change (KB) during request.")
    pod_ip = models.CharField(max_length=50, blank=True, default="")
    process_id = models.IntegerField(null=True, blank=True)
    thread_id = models.BigIntegerField(null=True, blank=True)
    # Not auto_now_add: rows are buffered, so the timestamp is set at request time.
    created_at = models.DateTimeField(default=timezone.now)
    # Indexing a datetime field can be expensive, so we also store the date separately for easier querying and partitioning.
    created_at_ymd = models.DateField(
        db_index=True, help_text="Date for easy querying and partitioning."
    )

    def __str__(self):
        return f"{self.method} {self.url} [{self.response_code}] {self.response_time}ms"


class RequestTimeLog(models.Model):
    request_id = models.UUIDField(db_index=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    url = models.CharField(max_length=500)
    normalized_url = models.CharField(max_length=255, db_index=True)
    message = models.CharField(max_length=255, blank=True, default="")
    func = models.CharField(max_length=100)
    filename = models.CharField(max_length=255)
    line = models.IntegerField()
    since_start = models.FloatField(help_text="Wall-clock ms since request start.")
    since_last = models.FloatField(help_text="Wall-clock ms since last checkpoint.")
    cpu_since_start = models.FloatField(help_text="CPU ms since request start.")
    cpu_since_last = models.FloatField(help_text="CPU ms since last checkpoint.")
    rss_delta = models.IntegerField(help_text="RSS change (KB) since last checkpoint.")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.normalized_url} +{self.since_last}ms — {self.message}"


class APIQueryLog(models.Model):
    request_id = models.UUIDField(db_index=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    url = models.CharField(max_length=500, db_index=True)
    normalized_url = models.CharField(max_length=255)
    query = models.TextField()
    query_time = models.FloatField(help_text="Query time in seconds.")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.normalized_url} {self.query_time}s"
