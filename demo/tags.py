# 사용자 취향과 장소 특징을 같은 기준으로 표현하기 위한 공통 태그 목록
ACTIVITY = ["체험", "사진", "굿즈", "관람", "음식"]
MOOD = ["귀여운", "조용한", "트렌디", "예술적", "레트로"]
TYPES = ["팝업", "카페", "전시"]
PRICE_LABEL = {0: "무료", 1: "1만원 이하", 2: "1~3만원", 3: "3만원 초과"}


def build_profile(answers):
    """취향 질문 답변(객관식)을 추천용 사용자 프로필로 변환한다. AI 없이 코드로 처리."""
    profile = {
        "activity": {t: 0.0 for t in ACTIVITY},
        "mood": {t: 0.0 for t in MOOD},
        "types": answers["types"],
        "max_price": answers["max_price"],
        "regions": answers.get("regions"),  # None이면 지역 무관
        "visit_date": answers["visit_date"],
    }
    # 1순위 1.0, 2순위 0.7, 3순위 0.4
    for weight, tag in zip([1.0, 0.7, 0.4], answers["activity_rank"]):
        profile["activity"][tag] = weight
    for weight, tag in zip([1.0, 0.7, 0.4], answers["mood_rank"]):
        profile["mood"][tag] = weight
    return profile
