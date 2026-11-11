"""Validate the complete CSV catalog before any production content is changed."""
import csv
import hashlib
import re
from pathlib import Path
from django.conf import settings
from django.core.management.base import CommandError
from core.management.commands.import_missions import normalize_korean_row
from core.services.logistics_curriculum import LOGISTICS_CURRICULUM
from core.services.mission_images import normalize_question_image_path, static_question_image_exists

SUBJECTS = ('logistics', 'realtor')
REQUIRED = {'문항ID','번호','과목','난이도','문제','보기1','보기2','보기3','보기4','보기5','정답','해설','사용여부','수정유형'}


def validate_catalog(root=None):
    root = Path(root or Path(settings.BASE_DIR)/'generated')
    catalog = {}
    errors = []
    seen = {}
    for subject in SUBJECTS:
        files = sorted(p for p in (root/subject).rglob('*') if p.is_file() and p.suffix.lower() == '.csv')
        if not files:
            errors.append(f'{subject}: CSV 파일이 없습니다. 전체 폴더 삭제 여부를 확인하세요.')
        catalog[subject] = []
        for path in files:
            ids = []
            try:
                with path.open(encoding='utf-8-sig', newline='') as f:
                    reader = csv.DictReader(f)
                    fields = reader.fieldnames or []
                    missing = REQUIRED - set(fields)
                    if missing or not {'챕터','분류코드'} & set(fields):
                        raise ValueError(f'필수 열 누락: {sorted(missing)}; 챕터 또는 분류코드 필요')
                    if len(fields) != len(set(fields)):
                        raise ValueError('열 이름 중복')
                    numbers = set()
                    for line, row in enumerate(reader, 2):
                        try:
                            if None in row or any(value is None for value in row.values()):
                                raise ValueError('CSV 열 개수가 맞지 않습니다. 쉼표·따옴표를 확인하세요.')
                            identity = row['문항ID'].strip()
                            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',identity):
                                raise ValueError('문항ID는 영문·숫자·하이픈·밑줄·점으로 100자 이하 작성하세요.')
                            if identity in seen:
                                raise ValueError(f'중복 문항ID {identity}; 기존 위치 {seen[identity]}')
                            seen[identity] = f'{path}:{line}'
                            if row['번호'].strip() in numbers:
                                raise ValueError('파일 안에서 번호가 중복됩니다.')
                            numbers.add(row['번호'].strip())
                            data = normalize_korean_row(row,csv_path=path,subject_code=subject)
                            if subject == 'logistics':
                                valid = {code: course['course'] for course in LOGISTICS_CURRICULUM for code,_ in course['chapters']}
                                if valid.get(data['chapter_code']) != data['course']:
                                    raise ValueError('과목과 챕터 코드가 일치하지 않습니다.')
                            if data['question_number'] < 1:
                                raise ValueError('번호는 1 이상의 정수여야 합니다.')
                            if not data['explanation'] or any(not row[f'보기{i}'].strip() for i in range(1,6)):
                                raise ValueError('보기 5개와 해설을 모두 작성하세요.')
                            image = data['image_raw_path']
                            if image and image != '없음' and not (normalize_question_image_path(image) and static_question_image_exists(normalize_question_image_path(image))):
                                raise ValueError(f'이미지 경로가 잘못되었거나 파일이 없습니다: {image}')
                            ids.append(identity)
                        except ValueError as error:
                            errors.append(f'{path}:{line}: {error}')
                    if not numbers:
                        errors.append(f'{path}: 빈 CSV입니다. 출제 중지는 행을 지우지 말고 사용여부=중지를 사용하세요.')
            except (OSError, UnicodeError, csv.Error, ValueError) as error:
                errors.append(f'{path}: {error}')
            catalog[subject].append((path, ids))
    if errors:
        raise CommandError('CSV 검증 실패:\n'+'\n'.join(errors))
    return catalog


def dependency_fingerprint():
    base = Path(settings.BASE_DIR)
    files = [base/'core/models.py']
    files += list((base/'core/management/commands').glob('import_missions.py'))
    files += [base/'core/services'/name for name in ('csv_catalog.py','generated_mission_sync.py','mission_images.py','mission_versioning.py','content_review.py','logistics_curriculum.py','realtor_curriculum.py','weaknesses.py','subjects.py')]
    files += [base/'core/management/commands/sync_content_catalog.py']
    files += list((base/'core/data').rglob('*.json'))
    files += [p for p in (base/'core/static/images/questions').rglob('*') if p.is_file()]
    h = hashlib.sha256(b'csv-sync-v1')
    for path in sorted(set(files)):
        h.update(str(path.relative_to(base)).encode()); h.update(path.read_bytes())
    return h.hexdigest()


def source_fingerprint(path, dependency):
    return hashlib.sha256(dependency.encode()+path.read_bytes()).hexdigest()
