# django-tracekit

Lightweight, production-safe Django APM — runtime-configurable request logging, per-step timing, and SQL query capture.

## What it does

| Middleware | What it captures |
|---|---|
| **APILogMiddleware** | Full request/response logging with CPU time, RSS memory, IP, headers, body |
| **TimingMiddleware** + **TimeLogger** | Per-step wall-clock, CPU, RSS checkpoints inside your views — with caller info via `inspect` |
| **APIQueryLogMiddleware** | Every SQL query executed during a request, with timing |

All three are **controlled at runtime** via a singleton Django admin model (`RuntimeConfig`) — no redeployment needed. You can filter by URL pattern, user ID, domain, time window, and sampling rate.

## Install

```bash
pip install django-tracekit
```

## Quick setup

```python
# settings.py

INSTALLED_APPS = [
    ...
    "tracekit",
]

MIDDLEWARE = [
    ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # ↓ tracekit middlewares — order matters
    "tracekit.middleware.request.RequestMiddleware",
    "tracekit.middleware.api_log.APILogMiddleware",
    "tracekit.middleware.timing.TimingMiddleware",
    "tracekit.middleware.query_log.APIQueryLogMiddleware",
]
```

```bash
python manage.py migrate
```

Then go to Django admin → **Tracekit runtime config** and toggle what you need.

## Using TimeLogger in your code

Drop `tl.log()` calls around slow sections to get per-step CPU/wall-clock/RSS breakdowns:

```python
from tracekit import get_time_log

def my_view(request):
    tl = get_time_log()

    data = expensive_query()
    tl.log("after expensive_query")

    result = heavy_computation(data)
    tl.log("after heavy_computation")

    return JsonResponse(result)
```

Checkpoints are bulk-written to `RequestTimeLog` at the end of the request. If TimeLogger isn't active for the current request (disabled in config, or outside the sampling window), `tl.log()` is a no-op.

## RuntimeConfig fields

### API Log
| Field | Default | Description |
|---|---|---|
| `api_log_enabled` | `False` | Master toggle |
| `api_log_url_filter` | `""` | Comma-separated normalized URLs to log (empty = all) |
| `api_log_user_id` | `0` | Only log this user (0 = all) |
| `api_log_capture_response_url` | `""` | URLs to capture response body for |
| `api_log_capture_response_user_id` | `0` | Capture response body for this user |
| `cpu_profiling_enabled` | `True` | Capture CPU time and RSS in API logs |

### Query Log
| Field | Default | Description |
|---|---|---|
| `query_log_enabled` | `False` | Master toggle |
| `query_log_url_filter` | `""` | Comma-separated normalized URLs to capture queries for |
| `query_log_user_id` | `0` | Only log queries for this user (0 = all) |
| `query_log_allowed_domains` | `""` | Domain whitelist (empty = all) |

### Time Logger
| Field | Default | Description |
|---|---|---|
| `time_log_url` | `""` | Normalized URL to instrument |
| `time_log_threshold` | `1.0` | Sampling rate (0.0–1.0) |
| `time_log_min_time` | `10` | Min step duration (ms) to record |
| `time_log_start` / `time_log_end` | `null` | Time window (server-local). Both must be set. |

### Log Rotation
| Field | Default | Description |
|---|---|---|
| `log_rotation_enabled` | `False` | Enable automatic purging of old records |

## Log rotation

Schedule the purge command to run daily:

```bash
# cron
30 5 * * * /path/to/python manage.py tracekit_purge_logs

# or with Celery beat
CELERY_BEAT_SCHEDULE = {
    'tracekit-purge-logs': {
        'task': 'tracekit.tasks.purge_logs',
        'schedule': crontab(hour=5, minute=30),
    },
}
```

The command reads `log_rotation_enabled` from RuntimeConfig. It deletes `APILog`, `RequestTimeLog`, and `APIQueryLog` records older than the retention period in batches. Use `--days` and `--batch-size` CLI flags to customize (defaults: 3 days, 10000 rows per batch).

```bash
# Override config from CLI
python manage.py tracekit_purge_logs --days 7 --batch-size 5000

# Dry run — see what would be deleted
python manage.py tracekit_purge_logs --dry-run

# Run even if rotation is disabled in config
python manage.py tracekit_purge_logs --force --days 1
```

If `log_rotation_enabled` is `False` (default), all data stays in one table forever — no purging happens.

## Settings

Optional overrides in your Django settings:

```python
TRACEKIT = {
    "REQUEST_ID_HEADER": "HTTP_X_REQUEST_ID",  # META key for request ID
    "HEALTH_CHECK_PATH": "/-/healthz/",         # Path to skip entirely
    "DB_ALIAS": "default",                       # Database for query capture
    "CONFIG_CACHE_KEY": "tracekit:config",       # Cache key for RuntimeConfig
    "CONFIG_CACHE_TIMEOUT": 300,                 # Cache TTL in seconds
    "CONFIG_CACHE_ALIAS": "default",             # Django cache backend to use
}
```

## How it differs from django-silk

| | django-tracekit | django-silk |
|---|---|---|
| **Production-safe** | Yes — runtime toggles, sampling, time windows | No — designed for development |
| **Per-step CPU/RSS** | Yes — `tl.log()` checkpoints with `resource.getrusage` | No |
| **Runtime control** | Django admin singleton, no redeploy | Config file changes |
| **Frontend** | None (query via admin/DB) | Built-in profiling UI |
| **Weight** | 4 middleware classes, 4 models | Large dependency tree |

## License

MIT
