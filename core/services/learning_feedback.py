from __future__ import annotations

from core.services.grading import parse_choice_schema
from core.services.learning_concepts import get_mission_learning_concept


def build_choice_feedback(mission, submitted_answer=""):
    explanations = mission.choice_explanations or {}
    if not isinstance(explanations, dict):
        explanations = {}

    submitted_key = str(submitted_answer or "").strip()
    correct_key = str(mission.correct_answer or "").strip()
    rows = []
    for choice in parse_choice_schema(mission.answer_schema):
        key = str(choice["key"])
        rows.append({
            "key": key,
            "label": choice["label"],
            "explanation": str(explanations.get(key, "") or "").strip(),
            "is_selected": key == submitted_key,
            "is_correct": key == correct_key,
        })
    return rows


def build_mission_feedback(mission, submitted_answer=""):
    choice_feedback = build_choice_feedback(mission, submitted_answer)
    correction_rows = [
        row for row in choice_feedback if row["is_selected"] or row["is_correct"]
    ]
    return {
        "choice_rows": choice_feedback,
        "has_choice_explanations": any(row["explanation"] for row in choice_feedback),
        "correction_rows": correction_rows,
        "learning_concept": get_mission_learning_concept(mission),
        "exam_tip": (mission.exam_tip or "").strip(),
    }
