"""Versioned review decisions, applied only to the exact inspected question text."""
import hashlib
import json
from datetime import date
from pathlib import Path

from django.db import transaction

from core.models import ConceptUnit, Mission

MANIFEST = Path(__file__).resolve().parents[1] / "data" / "logistics_review.json"


def load_review():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def content_fingerprint(mission):
    payload = [mission.prompt, mission.answer_schema, mission.correct_answer, mission.explanation]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


@transaction.atomic
def apply_review(mission, manifest=None):
    manifest = manifest or load_review()
    if not mission.subject_id or mission.subject.code != manifest["subject"]:
        return "out_of_scope"
    entry = manifest["missions"].get(mission.external_id)
    if not entry:
        if mission.review_status == Mission.REVIEW_CONFIRMED_ERROR:
            mission.is_usable_for_set = False
            mission.save(update_fields=["is_usable_for_set"])
            return "confirmed_error"
        update_fields = []
        if mission.review_status != Mission.REVIEW_UNREVIEWED:
            mission.review_status = Mission.REVIEW_UNREVIEWED
            update_fields.append("review_status")
        if mission.reviewed_on is not None or mission.concept_unit_id is not None:
            mission.reviewed_on = None
            mission.concept_unit = None
            update_fields.extend(["reviewed_on", "concept_unit"])
        if update_fields:
            mission.save(update_fields=update_fields)
        return "unreviewed"
    if content_fingerprint(mission) != entry["fingerprint"]:
        # Never carry the manifest's certification over to changed question text.
        if mission.review_status != Mission.REVIEW_CONFIRMED_ERROR:
            mission.review_status = Mission.REVIEW_UNREVIEWED
            mission.reviewed_on = None
            mission.concept_unit = None
            mission.save(update_fields=["review_status", "reviewed_on", "concept_unit"])
        if entry.get("hold") or mission.review_status == Mission.REVIEW_CONFIRMED_ERROR:
            mission.review_status = Mission.REVIEW_CONFIRMED_ERROR
            mission.is_usable_for_set = False
            mission.quality_note = "보류 문항이 변경되었습니다. 재검수 후 보류를 해제하세요."
            mission.save(update_fields=["review_status", "is_usable_for_set", "quality_note"])
        return "changed_since_review"
    if entry.get("hold"):
        mission.review_status = Mission.REVIEW_CONFIRMED_ERROR
        mission.is_usable_for_set = False
        mission.quality_note = entry["hold"]
        mission.save(update_fields=["review_status", "is_usable_for_set", "quality_note"])
        return "held"
    definition = manifest["concepts"][entry["concept"]]
    unit, _ = ConceptUnit.objects.update_or_create(
        subject=mission.subject, title=definition["title"],
        defaults={"comparison": definition["comparison"], "example": definition["example"],
                  "references": definition["references"],
                  "reviewed_on": date.fromisoformat(manifest["review_date"])},
    )
    mission.concept_unit = unit
    mission.reviewed_on = date.fromisoformat(manifest["review_date"])
    mission.review_status = Mission.REVIEW_VERIFIED
    mission.is_usable_for_set = True
    mission.quality_note = ""
    # Supporting references certify content, never invent an original exam source.
    mission.save(update_fields=[
        "concept_unit", "reviewed_on", "review_status", "is_usable_for_set", "quality_note",
    ])
    return "reviewed"
