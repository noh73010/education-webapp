import csv
import io
import subprocess
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from core.services.csv_catalog import validate_catalog


class Command(BaseCommand):
    help = 'Validate all maintained question CSVs without changing the database.'
    def add_arguments(self, parser):
        parser.add_argument('--source-root', default='')
        parser.add_argument('--base-ref', default='')
    def handle(self, *args, **options):
        root = options['source_root'] or None
        catalog = validate_catalog(root)
        ids = {identity for files in catalog.values() for _, rows in files for identity in rows}
        base_ref = options['base_ref']
        if base_ref and set(base_ref) != {'0'}:
            base = Path(settings.BASE_DIR)
            previous_ids = set()
            try:
                paths = subprocess.check_output(['git','ls-tree','-r','--name-only',base_ref,'--','generated/logistics','generated/realtor'],cwd=base,text=True).splitlines()
                for path in paths:
                    if not path.endswith('.csv'): continue
                    content = subprocess.check_output(['git','show',f'{base_ref}:{path}'],cwd=base).decode('utf-8-sig')
                    for row in csv.DictReader(io.StringIO(content)):
                        if row.get('문항ID'): previous_ids.add(row['문항ID'].strip())
                for identity in sorted(previous_ids-ids):
                    self.stdout.write(self.style.WARNING(f'WARNING missing ID {identity}: 삭제로 처리하지 않습니다. 사용여부=중지를 권장합니다.'))
            except (subprocess.CalledProcessError,UnicodeError):
                self.stdout.write(self.style.WARNING('WARNING: 이전 Git 버전의 누락 ID 비교를 수행하지 못했습니다.'))
        self.stdout.write(self.style.SUCCESS(f'CSV validation passed: files={sum(len(v) for v in catalog.values())}, IDs={len(ids)}'))
