"""Exact-version concept links. Changed CSV content requires another review."""
import json
from pathlib import Path
from functools import lru_cache
from datetime import date
from django.db import transaction
from core.models import ConceptUnit, Mission, Subject
from core.services.content_review import content_fingerprint

@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).resolve().parents[1]/'data/guided_concepts.json').read_text())


def concept_link_current(mission):
    for group in catalog():
        if mission.concept_unit and mission.concept_unit.title == group['title']:
            return (mission.subject.code == group['subject'] and
                    group['missions'].get(mission.external_id) == content_fingerprint(mission))
    return True


@transaction.atomic
def sync_guided_concepts():
    linked = held = 0
    for group in catalog():
        subject=Subject.objects.filter(code=group['subject']).first()
        if not subject:continue
        unit,_=ConceptUnit.objects.update_or_create(subject=subject,title=group['title'],defaults={
            'comparison':group['comparison'],'example':group['example'],'references':group['references'],
            'reviewed_on':date.fromisoformat(group['reviewed_on'])})
        for m in Mission.objects.filter(subject=subject,external_id__in=group['missions']):
            if content_fingerprint(m)==group['missions'][m.external_id] and m.is_usable_for_set and m.source_enabled:
                m.concept_unit=unit;m.save(update_fields=['concept_unit']);linked+=1
            else:
                if m.concept_unit_id==unit.pk:
                    m.concept_unit=None;m.save(update_fields=['concept_unit'])
                held+=1
    return linked,held
