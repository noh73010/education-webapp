"""Atomic, validated and incremental deployment import for the maintained catalog."""
from io import StringIO
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import ContentSourceSync, Mission, Subject
from core.services.csv_catalog import validate_catalog, dependency_fingerprint, source_fingerprint
from core.services.generated_mission_sync import parse_import_counts
from core.management.commands.import_missions import sync_generated_problem_sets


class Command(BaseCommand):
    help = 'Validate the entire catalog, then atomically import changed files only.'
    def add_arguments(self, parser):
        parser.add_argument('--source-root', default='')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--force', action='store_true')
    @transaction.atomic
    def handle(self, *args, **options):
        catalog = validate_catalog(options['source_root'] or None)
        dependency = dependency_fingerprint()
        current_ids = {identity for files in catalog.values() for _, ids in files for identity in ids}
        previous_ids = {identity for marker in ContentSourceSync.objects.all() for identity in marker.mission_ids}
        for identity in sorted(previous_ids-current_ids):
            self.stdout.write(self.style.WARNING(f'WARNING missing ID {identity}: DB 기록 유지. 출제 중지는 CSV 사용여부=중지를 이용하세요.'))
        changed = unchanged = 0
        # Serialize deploy/import jobs on the same catalog. New DBs have subject
        # rows from migrations, so this also works before checkpoint creation.
        list(Subject.objects.select_for_update().filter(code__in=catalog).order_by('pk'))
        for subject_code, files in catalog.items():
            subject = Subject.objects.get(code=subject_code)
            subject_changed = False
            for path, ids in files:
                path_key = str(path.resolve().relative_to(Path(settings.BASE_DIR).resolve())) if path.resolve().is_relative_to(Path(settings.BASE_DIR).resolve()) else str(path.resolve())
                digest = source_fingerprint(path,dependency)
                marker = ContentSourceSync.objects.filter(source_path=path_key).first()
                if marker and marker.fingerprint == digest and not options['force']:
                    unchanged += 1
                    self.stdout.write(f'UNCHANGED {path_key}')
                    continue
                before = {m.external_id:(m.content_fingerprint,m.source_enabled) for m in Mission.objects.filter(external_id__in=ids)}
                stdout, stderr = StringIO(), StringIO()
                call_command('import_missions',str(path),subject_code=subject_code,skip_unchanged=True,stdout=stdout,stderr=stderr)
                detail = stdout.getvalue()
                counts = parse_import_counts(detail)
                if 'SKIP ' in detail or 'missing=' in detail and 'missing=0' not in detail:
                    raise CommandError(f'{path_key}: 일부 행 또는 이미지 반영 실패. 전체 변경을 취소합니다.\n{detail}')
                for mission in Mission.objects.filter(external_id__in=ids).order_by('external_id'):
                    previous = before.get(mission.external_id)
                    if not mission.source_enabled:
                        status = '중지'
                    elif previous is None:
                        status = '추가'
                    elif previous != (mission.content_fingerprint,mission.source_enabled):
                        status = '수정'
                    else:
                        continue
                    self.stdout.write(f'{status} {mission.external_id} · 버전 {mission.content_version}')
                ContentSourceSync.objects.update_or_create(source_path=path_key,defaults={
                    'subject_code':subject_code,'fingerprint':digest,'mission_ids':sorted(set(ids) | set(marker.mission_ids if marker else []))})
                changed += 1
                subject_changed = True
                self.stdout.write(f'IMPORTED {path_key}: created={counts.created}, updated={counts.updated}, invalidated_attempts={counts.invalidated_attempts}')
            if subject_changed:
                sync_generated_problem_sets(list(Mission.objects.filter(subject=subject).exclude(course='').exclude(chapter_code='')))
        if options['dry_run']:
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(f'Catalog sync complete: changed_files={changed}, unchanged_files={unchanged}, dry_run={options["dry_run"]}'))
