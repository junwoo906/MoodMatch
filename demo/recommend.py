"""MoodMatch 추천 데모: 사용자가 문장으로 말한 기분·취향과 장소 소개글의 의미 유사도로 추천한다.

무료 로컬 임베딩 모델을 사용하므로 API 비용이 들지 않는다. (처음 실행 시 모델을 한 번 내려받음)
"""
import json
import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer, util

sys.stdout.reconfigure(encoding="utf-8")

MODEL = "jhgan/ko-sroberta-multitask"  # 한국어 문장 임베딩 모델 (무료)


def is_open(place, day):
    """방문일에 운영 중인지 확인 (상설 장소는 기간이 없음)"""
    if place["start"] and day < place["start"]:
        return False, "방문일에 아직 시작 전"
    if place["end"] and day > place["end"]:
        return False, "운영 종료"
    return True, ""


def recommend(model, places, request, top_n=3):
    """1) 조건 필터(날짜·지역·예산)는 코드로 거르고 2) 남은 곳을 의미 유사도 순으로 정렬한다."""
    candidates, excluded = [], []
    for p in places:
        ok, why = is_open(p, request["date"])
        if ok and request.get("regions") and p["region"] not in request["regions"]:
            ok, why = False, "지역 불일치"
        if ok and p["price"] > request["budget"]:
            ok, why = False, "예산 초과"
        (candidates if ok else excluded).append(p if ok else (p["name"], why))

    query = model.encode(request["mood"], convert_to_tensor=True)
    docs = model.encode([p["desc"] for p in candidates], convert_to_tensor=True)
    scores = util.cos_sim(query, docs)[0].tolist()
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return ranked[:top_n], excluded


REQUESTS = [
    {"who": "사용자 A", "mood": "친구랑 귀여운 거 보면서 사진 많이 찍고 굿즈도 사고 싶어",
     "date": "2026-10-31", "regions": None, "budget": 10000},
    {"who": "사용자 B", "mood": "혼자 조용하게 작품 감상하면서 생각 정리하고 싶어",
     "date": "2026-10-31", "regions": None, "budget": 30000},
]

if __name__ == "__main__":
    places = json.loads(Path(__file__).with_name("places.json").read_text(encoding="utf-8"))
    model = SentenceTransformer(MODEL)
    for req in REQUESTS:
        top, excluded = recommend(model, places, req)
        print(f"\n=== {req['who']}: \"{req['mood']}\" (방문일 {req['date']}, 예산 {req['budget']:,}원) ===")
        for i, (p, s) in enumerate(top, 1):
            print(f"{i}. {p['name']} ({p['region']}, {p['price']:,}원)  유사도 {s:.2f}")
        print("제외:", "; ".join(f"{n}({why})" for n, why in excluded))
