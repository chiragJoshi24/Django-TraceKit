from django.contrib import admin

from tracekit.models import APILog, APIQueryLog, RequestTimeLog, RuntimeConfig


@admin.register(RuntimeConfig)
class RuntimeConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        ("API Log", {
            "fields": (
                "api_log_enabled",
                "api_log_url_filter",
                "api_log_user_id",
                "api_log_capture_response_url",
                "api_log_capture_response_user_id",
                "cpu_profiling_enabled",
            ),
        }),
        ("Query Log", {
            "fields": (
                "query_log_enabled",
                "query_log_url_filter",
                "query_log_user_id",
                "query_log_allowed_domains",
            ),
        }),
        ("Time Logger", {
            "fields": (
                "time_log_url",
                "time_log_threshold",
                "time_log_min_time",
                "time_log_start",
                "time_log_end",
            ),
        }),
    )

    def has_add_permission(self, request):
        # Singleton — only allow add if none exists.
        return not RuntimeConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(APILog)
class APILogAdmin(admin.ModelAdmin):
    list_display = (
        "method", "url", "response_code", "response_time",
        "user_id", "request_ip", "created_at",
    )
    list_filter = ("method", "response_code", "created_at")
    search_fields = ("url", "full_url", "request_ip", "user_id")
    readonly_fields = (
        "request_id", "user_id", "method", "url", "full_url",
        "request_ip", "request_headers", "request_body",
        "response_code", "response_headers", "response_body",
        "response_time", "cpu_time", "rss_before", "rss_delta",
        "pod_ip", "process_id", "thread_id", "created_at",
    )


@admin.register(RequestTimeLog)
class RequestTimeLogAdmin(admin.ModelAdmin):
    list_display = (
        "normalized_url", "message", "func", "since_last",
        "cpu_since_last", "user_id", "created_at",
    )
    list_filter = ("normalized_url", "created_at")
    search_fields = ("url", "normalized_url", "message", "func")
    readonly_fields = (
        "request_id", "user_id", "url", "normalized_url", "message",
        "func", "filename", "line", "since_start", "since_last",
        "cpu_since_start", "cpu_since_last", "rss_delta", "created_at",
    )


@admin.register(APIQueryLog)
class APIQueryLogAdmin(admin.ModelAdmin):
    list_display = (
        "normalized_url", "query_time", "user_id", "created_at",
    )
    list_filter = ("normalized_url", "created_at")
    search_fields = ("url", "normalized_url", "query")
    readonly_fields = (
        "request_id", "user_id", "url", "normalized_url",
        "query", "query_time", "created_at",
    )
