"""
Optional Celery task for log rotation.

If your project uses Celery, add to your beat schedule:

    CELERY_BEAT_SCHEDULE = {
        'tracekit-purge-logs': {
            'task': 'tracekit.tasks.purge_logs',
            'schedule': crontab(hour=5, minute=30),
        },
    }

If you don't use Celery, schedule the management command instead:
    30 5 * * * python manage.py tracekit_purge_logs
"""

import logging

logger = logging.getLogger("tracekit")

try:
    from celery import shared_task

    @shared_task(name="tracekit.tasks.purge_logs")
    def purge_logs():
        """Celery wrapper around the purge management command."""
        from django.core.management import call_command

        call_command("tracekit_purge_logs")

except ImportError:
    # Celery not installed — this is fine, users can use the
    # management command directly.
    pass
