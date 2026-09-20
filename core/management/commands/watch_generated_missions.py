"""Watch generated question sources outside the web request lifecycle."""

from pathlib import Path
import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from core.services.generated_mission_watch import generated_sources_fingerprint
from core.services.subjects import LOGISTICS_SUBJECT_CODE


class Command(BaseCommand):
    help = (
        "Watch generated CSV/image sources and run the idempotent mission sync "
        "when their fingerprint changes. Run this as a separate process."
    )

    def add_arguments(self, parser):
        parser.add_argument("--subject-code", default=LOGISTICS_SUBJECT_CODE)
        parser.add_argument("--source-dir", default="")
        parser.add_argument("--image-dir", default="")
        parser.add_argument(
            "--once",
            action="store_true",
            help="Check and synchronize once, then exit (useful for operations/tests).",
        )

    def handle(self, *args, **options):
        subject_code = options["subject_code"].strip()
        source_dir = Path(options["source_dir"] or settings.BASE_DIR / "generated" / subject_code)
        image_dir = Path(
            options["image_dir"]
            or settings.BASE_DIR / "core" / "static" / "images" / "questions" / subject_code
        )
        interval = settings.GENERATED_MISSION_WATCH_INTERVAL_SECONDS
        previous_fingerprint = None

        self.stdout.write(
            f"Watching generated missions: subject={subject_code}, interval={interval}s, "
            f"source={source_dir}, images={image_dir}"
        )
        while True:
            current_fingerprint = generated_sources_fingerprint(source_dir, image_dir)
            if current_fingerprint != previous_fingerprint:
                try:
                    call_command(
                        "sync_generated_missions",
                        subject_code=subject_code,
                        source_dir=str(source_dir),
                        create_problem_sets=True,
                        fail_on_error=True,
                        stdout=self.stdout,
                        stderr=self.stderr,
                    )
                except CommandError as error:
                    self.stderr.write(self.style.ERROR(f"Generated sync failed; will retry: {error}"))
                    if options["once"]:
                        raise
                else:
                    previous_fingerprint = current_fingerprint
                    self.stdout.write(self.style.SUCCESS(
                        f"Generated sources synchronized: {current_fingerprint[:12]}"
                    ))

            if options["once"]:
                return
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write("Generated mission watcher stopped.")
                return
