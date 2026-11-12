"""Optimistic writes keep a stale tab/device from overwriting a newer draft."""
from django.utils.dateparse import parse_datetime

CONFLICT_MESSAGE = '다른 탭이나 기기에서 답안이 변경됐어요. 새로고침해 최신 답안을 확인한 뒤 다시 제출해 주세요.'


def revision_conflicts(request, updated_at):
    if 'draft_revision' not in request.POST:
        return False  # Legacy clients retain the existing submission contract.
    raw = request.POST.get('draft_revision', '')
    if updated_at is None:
        return bool(raw)
    try:
        return parse_datetime(raw) != updated_at
    except (TypeError, ValueError):
        return True
