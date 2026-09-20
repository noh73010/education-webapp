"""Synchronize generated CSV content without coupling it to web startup."""

from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.commands.import_missions import sync_generated_problem_sets
from core.models import Mission, Subject
from core.services.generated_mission_sync import (
    parse_import_counts,
    sync_generated_csvs,
)
from core.services.subjects import LOGISTICS_SUBJECT_CODE


class Command(BaseCommand):
    help = (
        "Safely synchronize every generated mission CSV, isolating failures "
        "per file. This command is never run from a web request or AppConfig."
    )

    def add_arguments(self, parser):
        parser.add_argument("--subject-code", default=LOGISTICS_SUBJECT_CODE)
        parser.add_argument(
            "--source-dir",
            default="",
            help="Default: <project root>/generated/<subject-code>",
        )
        parser.add_argument("--create-problem-sets", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--fail-on-error",
            action="store_true",
            help="Return a non-zero exit after processing all files if any file failed.",
        )

    def handle(self, *args, **options):
        subject_code = options["subject_code"].strip()
        try:
            subject = Subject.objects.get(code=subject_code)
        except Subject.DoesNotExist as error:
            raise CommandError(f"Unknown subject code: {subject_code}") from error

        source_dir = (
            Path(options["source_dir"])
            if options["source_dir"]
            else Path(settings.BASE_DIR) / "generated" / subject.code
        )

        def import_file(csv_path):
            stdout = StringIO()
            stderr = StringIO()
            call_command(
                "import_missions",
                str(csv_path),
                subject_code=subject.code,
                dry_run=options["dry_run"],
                stdout=stdout,
                stderr=stderr,
            )
            output = stdout.getvalue()
            details = "\n".join(
                line.strip()
                for line in f"{output}\n{stderr.getvalue()}".splitlines()
                if line.strip() and "Import complete:" not in line
            )
            return parse_import_counts(output), details

        try:
            report = sync_generated_csvs(source_dir, import_file=import_file)
        except ValueError as error:
            raise CommandError(str(error)) from error

        for result in report.results:
            relative_path = result.path.relative_to(report.source_dir)
            if result.succeeded:
                self.stdout.write(
                    f"FILE {relative_path}: created={result.counts.created}, "
                    f"updated={result.counts.updated}, skipped={result.counts.skipped}, errors=0, "
                    f"invalidated_attempts={result.counts.invalidated_attempts}, "
                    f"affected_users={result.counts.affected_users}"
                )
                for detail in result.details.splitlines():
                    self.stdout.write(f"  {detail}")
            else:
                self.stderr.write(
                    self.style.ERROR(f"FILE {relative_path}: created=0, updated=0, skipped=0, errors=1")
                )
                self.stderr.write(self.style.ERROR(f"  {result.error}"))

        set_created = set_updated = set_deactivated = 0
        successful_files = report.counts.files
        if options["create_problem_sets"] and successful_files:
            missions = list(
                Mission.objects.filter(subject=subject)
                .exclude(course="")
                .exclude(chapter_code="")
                .order_by("course", "chapter_code", "external_id")
            )
            with transaction.atomic():
                set_created, set_updated, set_deactivated = sync_generated_problem_sets(missions)
                if options["dry_run"]:
                    transaction.set_rollback(True)

        summary = (
            "Generated sync complete: "
            f"files={len(report.results)}, created={report.counts.created}, "
            f"updated={report.counts.updated}, skipped={report.counts.skipped}, "
            f"errors={report.errors}, invalidated_attempts={report.counts.invalidated_attempts}, "
            f"affected_users={report.counts.affected_users}, sets_created={set_created}, "
            f"sets_updated={set_updated}, sets_deactivated={set_deactivated}, "
            f"dry_run={options['dry_run']}"
        )
        if report.errors:
            self.stdout.write(self.style.WARNING(summary))
            if options["fail_on_error"]:
                raise CommandError(f"Generated mission sync completed with {report.errors} file error(s)")
        else:
            self.stdout.write(self.style.SUCCESS(summary))
