"""Audit every stored prompt without altering questions or learning history."""
import json
import re
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from core.models import Mission
from core.services.question_layout import question_blocks


class Command(BaseCommand):
    help = 'Verify question layout preserves source text; optionally export each question and its blocks.'

    def add_arguments(self, parser):
        parser.add_argument('--output', help='Optional JSON report path (for content editors).')

    def handle(self, *args, **options):
        counts, rows, failures = Counter(), [], []
        compact = lambda text: re.sub(r'\s+', '', text)
        for mission in Mission.objects.order_by('subject_id', 'external_id', 'pk').iterator():
            blocks = question_blocks(mission.prompt)
            # Structured control tags are presentation metadata, not question text.
            original = re.sub(r'\[/?(?:CONTEXT|TABLE|DATA|RULES|TEXT|QUESTION)\]', '', mission.prompt, flags=re.I)
            intact = compact(original) == compact(''.join(b['content'] for b in blocks))
            if not intact:
                failures.append(mission.external_id or str(mission.pk))
            counts.update(set(b['type'] for b in blocks))
            rows.append({'id': mission.external_id or mission.pk, 'subject': mission.subject_id,
                         'source_preserved': intact, 'blocks': blocks})
        if options['output']:
            Path(options['output']).write_text(json.dumps({'counts': dict(counts), 'questions': rows},
                                                       ensure_ascii=False, indent=2), encoding='utf-8')
        if failures:
            raise CommandError('Layout text mismatch: ' + ', '.join(failures))
        self.stdout.write(self.style.SUCCESS(f'Question layout audit passed: {len(rows)} prompts; source text preserved.'))
        self.stdout.write(json.dumps(dict(sorted(counts.items())), ensure_ascii=False))
