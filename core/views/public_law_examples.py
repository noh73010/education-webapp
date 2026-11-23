from django.shortcuts import render
from django.views.decorators.http import require_safe
from django.views.decorators.cache import never_cache

from core.views.guest_practice import track_blog


EXAMPLES = {
    "land-zones": {
        "title": "용도지역·용도지구·용도구역 구별 문제",
        "intro": "주거지역·고도지구·개발제한구역이 각각 어느 분류에 속하는지 구별해 보세요.",
        "question": "주거지역, 고도지구, 개발제한구역을 순서대로 분류한 것으로 옳은 것은?",
        "choices": ("용도지구 → 용도지역 → 용도구역", "용도지역 → 용도지구 → 용도구역", "용도지역 → 용도구역 → 용도지구"),
        "answer": "② 용도지역 → 용도지구 → 용도구역",
        "explanation": "주거지역은 용도지역 중 도시지역을 세분한 것입니다. 고도지구는 건축물 높이를 규율하는 용도지구입니다. 개발제한구역은 용도구역입니다. ①은 지역과 지구를, ③은 지구와 구역을 바꿨습니다. 이 문제는 지정 명칭의 분류만 묻고 실제 필지의 건축 가능 여부는 묻지 않습니다.",
        "law": "국토의 계획 및 이용에 관한 법률 제36~38조",
        "law_url": "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1028408089",
        "course_label": "용도지역·지구·구역 관련 단원",
        "campaign": "realtor-quiz-zones",
    },
    "land-readjustment": {
        "title": "도시개발법 수용·사용과 환지방식 구별 문제",
        "intro": "사업에 필요한 토지를 수용·사용하는 방식과 종전 토지를 재배치하는 환지방식을 구별해 보세요.",
        "question": "도시개발사업의 시행 방식에 관한 설명으로 옳은 것은?",
        "choices": ("도시개발사업은 환지방식으로만 시행할 수 있다.", "수용과 환지는 구분되지만 하나의 사업에서 혼용할 수 없다.", "수용 또는 사용의 방식, 환지방식 또는 이를 혼용하는 방식이 가능하다."),
        "answer": "③ 수용 또는 사용, 환지, 혼용 방식이 가능합니다.",
        "explanation": "도시개발법은 환지방식만 허용하지 않으므로 ①은 틀립니다. 두 방식을 혼용할 수도 있으므로 ②도 틀립니다. 구체적으로 어느 사업에 어떤 방식을 택할 수 있는지는 법령상 요건을 별도로 확인해야 합니다.",
        "law": "도시개발법 제21조",
        "law_url": "https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029378289",
        "course_label": "도시개발법 단원",
        "campaign": "realtor-quiz-readjustment",
    },
}


@never_cache
@require_safe
def public_law_example(request, topic):
    example = EXAMPLES[topic]
    if request.method == "GET" and not request.user.is_authenticated:
        seen = request.session.get("public_quiz_arrivals", [])
        if topic not in seen:
            track_blog("quiz_arrival", example["campaign"])
            request.session["public_quiz_arrivals"] = [*seen, topic]
    return render(request, "core/public_law_example.html", example)
