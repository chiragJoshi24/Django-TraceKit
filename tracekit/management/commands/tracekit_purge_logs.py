"""
Management command to purge old tracekit log records.

Schedule this via cron, Celery beat, or any task scheduler:

    # cron — every day at 5:30 AM
    30 5 * * * /path/to/python manage.py tracekit_purge_logs

    # Celery beat
    'tracekit-purge-logs': {
        'task': 'tracekit.tasks.purge_logs',
        'schedule': crontab(hour=5, minute=30),
    }

Behaviour:
    1. Reads RuntimeConfig to check if rotation is enabled.
    2. Deletes APILog, RequestTimeLog, and APIQueryLog rows older than
       the given retention days in batches to avoid locking the table.
    3. Defaults: 3 days retention, 10 000 row batch size.
       Override with --days and --batch-size flags.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from tracekit.models import APILog, APIQueryLog, RequestTimeLog, RuntimeConfig


class Command(BaseCommand):
    help = "Purge tracekit log records older than the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override retention days from RuntimeConfig.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=None,
            help="Override batch size from RuntimeConfig.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if log_rotation_enabled is False in RuntimeConfig.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be deleted without actually deleting.",
        )

    def handle(self, *args, **options):
        config = RuntimeConfig.load()

        if not config.log_rotation_enabled and not options["force"]:
            self.stdout.write(
                "Log rotation is disabled in RuntimeConfig. "
                "Use --force to run anyway."
            )
            return

        days = options["days"] or 3
        batch_size = options["batch_size"] or 10000
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timezone.timedelta(days=days)

        self.stdout.write(
            f"Purging records older than {days} day(s) "
            f"(before {cutoff.isoformat()}) "
            f"in batches of {batch_size}"
            f"{' [DRY RUN]' if dry_run else ''}"
        )

        models = [
            ("APILog", APILog),
            ("RequestTimeLog", RequestTimeLog),
            ("APIQueryLog", APIQueryLog),
        ]

        for name, model in models:
            total = self._purge_model(model, cutoff, batch_size, dry_run)
            self.stdout.write(f"  {name}: {total} row(s) {'would be ' if dry_run else ''}deleted")

        self.stdout.write(self.style.SUCCESS("Done."))

    def _purge_model(self, model, cutoff, batch_size, dry_run):
        """Delete old records in batches. Returns total rows deleted."""
        total = 0
        while True:
            # Subquery: find PKs of a batch of old rows
            pks = list(
                model.objects.filter(created_at__lt=cutoff)
                .values_list("pk", flat=True)[:batch_size]
            )
            if not pks:
                break

            if dry_run:
                total += len(pks)
                if len(pks) < batch_size:
                    break
                continue

            deleted, _ = model.objects.filter(pk__in=pks).delete()
            total += deleted

            if len(pks) < batch_size:
                break  # last batch

        return total
