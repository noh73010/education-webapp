import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DatabaseError
from django.db.migrations.recorder import MigrationRecorder
from django.template.loader import get_template
from django.urls import NoReverseMatch, reverse

from core.models import Mission, ProblemSet, UserEvent


class Command(BaseCommand):
    help = "Run a read-only smoke check for launch readiness."

    URL_NAMES = [
        "landing",
        "signup",
        "login",
        "mission_list",
        "stats",
        "wrong_notes",
        "problem_set_list",
        "exam_start",
        "premium_info",
        "admin_dashboard",
        "inquiry",
    ]

    TEMPLATE_NAMES = [
        "core/landing.html",
        "registration/signup.html",
        "registration/login.html",
        "core/mission_list.html",
        "core/premium_info.html",
        "core/admin_dashboard.html",
        "core/inquiry_form.html",
        "core/inquiry_done.html",
        "404.html",
        "500.html",
    ]

    def handle(self, *args, **options):
        self.fail_count = 0
        self.warning_count = 0

        self.stdout.write("SMOKE CHECK START")
        self.stdout.write("")

        self.check_database_state()
        self.check_migration_state()
        self.check_production_environment()
        self.check_url_reverse()
        self.check_templates()
        self.check_quality_state()
        self.check_admin_users()

        self.stdout.write("")
        self.stdout.write(f"Warnings: {self.warning_count}")
        self.stdout.write(f"Failures: {self.fail_count}")

        if self.fail_count:
            self.stdout.write(self.style.ERROR("SMOKE CHECK FAILED"))
        else:
            self.stdout.write(self.style.SUCCESS("SMOKE CHECK PASSED"))

    def ok(self, message):
        self.stdout.write(self.style.SUCCESS(f"OK - {message}"))

    def warning(self, message):
        self.warning_count += 1
        self.stdout.write(self.style.WARNING(f"WARNING - {message}"))

    def fail(self, message):
        self.fail_count += 1
        self.stdout.write(self.style.ERROR(f"FAIL - {message}"))

    def check_database_state(self):
        self.stdout.write("[1] DB basic state")

        mission_count = Mission.objects.count()
        usable_mission_count = Mission.objects.filter(is_usable_for_set=True).count()
        practical_mission_count = Mission.objects.filter(quality_level="practical").count()
        problem_set_count = ProblemSet.objects.count()

        self.ok(f"Mission total: {mission_count}")
        self.ok(f"Usable Mission: {usable_mission_count}")
        self.ok(f"Practical Mission: {practical_mission_count}")
        self.ok(f"ProblemSet total: {problem_set_count}")

        try:
            UserEvent.objects.exists()
        except DatabaseError as exc:
            self.fail(f"UserEvent table is not accessible: {exc.__class__.__name__}")
        else:
            self.ok("UserEvent table is accessible")

        self.stdout.write("")

    def check_migration_state(self):
        self.stdout.write("[2] Migration state")

        try:
            applied_migrations = set(
                MigrationRecorder.Migration.objects.values_list("app", "name")
            )
        except DatabaseError as exc:
            self.fail(f"Could not read django_migrations: {exc.__class__.__name__}")
            self.stdout.write("")
            return

        if ("core", "0028_userevent") in applied_migrations:
            self.ok("UserEvent migration is applied: core.0028_userevent")
        else:
            self.fail("UserEvent migration is not applied: run manage.py migrate")

        migration_dir = Path(__file__).resolve().parents[2] / "migrations"
        inquiry_migration_files = [
            path.stem for path in migration_dir.glob("*.py")
            if "inquiry" in path.stem.lower()
        ]
        if inquiry_migration_files:
            missing_inquiry_migrations = [
                name for name in inquiry_migration_files
                if ("core", name) not in applied_migrations
            ]
            if missing_inquiry_migrations:
                self.fail(
                    "Inquiry migration exists but is not applied: "
                    f"{', '.join(sorted(missing_inquiry_migrations))}"
                )
            else:
                self.ok(
                    "Inquiry migration is applied: "
                    f"{', '.join(sorted(inquiry_migration_files))}"
                )
        else:
            self.ok("No Inquiry migration found")

        self.stdout.write("")

    def check_production_environment(self):
        self.stdout.write("[3] Production environment")

        if settings.DEBUG:
            self.warning("DEBUG is currently enabled. Production must use DJANGO_DEBUG=0")
            self.stdout.write("")
            return

        required_env_vars = [
            "DJANGO_SECRET_KEY",
            "DJANGO_ALLOWED_HOSTS",
            "DJANGO_CSRF_TRUSTED_ORIGINS",
        ]
        for name in required_env_vars:
            if os.environ.get(name):
                self.ok(f"{name} is set")
            else:
                self.fail(f"{name} is missing while DEBUG=0")

        if settings.ALLOWED_HOSTS:
            self.ok(f"ALLOWED_HOSTS configured: {', '.join(settings.ALLOWED_HOSTS)}")
        else:
            self.fail("ALLOWED_HOSTS is empty while DEBUG=0")

        if getattr(settings, "CSRF_TRUSTED_ORIGINS", None):
            self.ok("CSRF_TRUSTED_ORIGINS configured")
        else:
            self.fail("CSRF_TRUSTED_ORIGINS is empty while DEBUG=0")

        self.stdout.write("")

    def check_url_reverse(self):
        self.stdout.write("[4] URL reverse")

        for url_name in self.URL_NAMES:
            try:
                resolved = reverse(url_name)
            except NoReverseMatch as exc:
                self.fail(f"{url_name}: {exc}")
            else:
                self.ok(f"{url_name}: {resolved}")

        self.stdout.write("")

    def check_templates(self):
        self.stdout.write("[5] Template loading")

        for template_name in self.TEMPLATE_NAMES:
            try:
                get_template(template_name)
            except Exception as exc:
                self.fail(f"{template_name}: {exc.__class__.__name__}")
            else:
                self.ok(template_name)

        self.stdout.write("")

    def check_quality_state(self):
        self.stdout.write("[6] Mission quality state")

        basic_usable_count = Mission.objects.filter(
            quality_level="basic",
            is_usable_for_set=True,
        ).count()
        if basic_usable_count:
            self.fail(f"Basic missions exposed as usable: {basic_usable_count}")
        else:
            self.ok("No basic missions are exposed as usable")

        usable_mission_count = Mission.objects.filter(is_usable_for_set=True).count()
        practical_mission_count = Mission.objects.filter(quality_level="practical").count()
        mission_count = Mission.objects.count()
        unchecked_count = Mission.objects.filter(is_quality_checked=False).count()

        if usable_mission_count < 10:
            self.warning(f"Usable Mission count is low: {usable_mission_count}")
        else:
            self.ok(f"Usable Mission count is sufficient: {usable_mission_count}")

        if practical_mission_count < 10:
            self.warning(f"Practical Mission count is low: {practical_mission_count}")
        else:
            self.ok(f"Practical Mission count is sufficient: {practical_mission_count}")

        unchecked_ratio = (unchecked_count / mission_count) if mission_count else 0
        if unchecked_count > 10 and unchecked_ratio > 0.2:
            self.warning(
                "Unchecked Mission count is high: "
                f"{unchecked_count}/{mission_count} ({unchecked_ratio:.1%})"
            )
        else:
            self.ok(f"Unchecked Mission count: {unchecked_count}/{mission_count}")

        self.stdout.write("")

    def check_admin_users(self):
        self.stdout.write("[7] Admin user state")

        User = get_user_model()
        staff_count = User.objects.filter(is_staff=True).count()

        if staff_count:
            self.ok(f"Staff users: {staff_count}")
        else:
            self.warning("No staff user exists")
