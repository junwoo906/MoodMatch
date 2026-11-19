"""MoodMatch 추천 데모: 취향 질문지 답변(객관식)과 장소 소개글의 의미 유사도로 추천한다.

보기마다 설명 문장을 미리 정해 두고, 그 문장과 장소 소개글을 무료 로컬 임베딩 모델로 비교한다.
장소마다 태그를 붙일 필요가 없고 API 비용도 들지 않는다. (처음 실행 시 모델을 한 번 내려받음)
"""
import json
import sys
from datetime import date
from pathlib import Path

from sentence_transformers import SentenceTransformer, util

sys.stdout.reconfigure(encoding="utf-8")

MODEL = "jhgan/ko-sroberta-multitask"  # 한국어 문장 임베딩 모델 (무료)

# 질문지 보기 → 설명 문장 (장소 소개글과 비교할 기준)
OPTION_TEXT = {
    # Q2. 가서 뭘 하고 싶어요?
    "체험": "직접 참여하고 만들어 보는 체험을 할 수 있는 곳",
    "사진": "예쁜 포토존에서 사진을 많이 찍을 수 있는 곳",
    "굿즈": "한정판 굿즈와 기념품을 살 수 있는 곳",
    "관람": "작품이나 전시를 천천히 감상할 수 있는 곳",
    "음식": "맛있는 디저트와 음료를 먹을 수 있는 곳",
    # Q3. 원하는 분위기는?
    "귀여운": "귀여운 캐릭터가 있는 아기자기한 분위기",
    "조용한": "사람이 적고 조용하고 차분한 분위기",
    "트렌디": "요즘 유행하는 감각적이고 힙한 분위기",
    "예술적": "예술 작품과 감성이 느껴지는 분위기",
    "레트로": "옛날 감성이 느껴지는 레트로 분위기",
    # Q4. 누구랑 가요?
    "혼자": "혼자 여유롭게 시간을 보내기 좋은 곳",
    "친구": "친구와 함께 즐기기 좋은 곳",
    "연인": "연인과 데이트하기 좋은 곳",
    "가족": "가족과 함께 가기 좋은 곳",
}
RANK_WEIGHT = [1.0, 0.7, 0.4]  # 1순위, 2순위, 3순위
PLACES_FILE = Path(__file__).with_name("places.json")


def load_model():
    """임베딩 모델을 불러온다. 느리므로 프로그램에서 한 번만 불러서 재사용한다."""
    return SentenceTransformer(MODEL)


def load_places(path=PLACES_FILE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def is_open(place, day):
    """방문일에 운영 중인지 확인 (상설 장소는 기간이 없음)"""
    if place["start"] and day < place["start"]:
        return False, "방문일에 아직 시작 전"
    if place["end"] and day > place["end"]:
        return False, "운영 종료"
    return True, ""


def answer_weights(ans):
    """질문지 답변을 (보기, 가중치) 목록으로 바꾼다."""
    picks = []
    for key in ("activity_rank", "mood_rank"):
        picks += list(zip(ans[key], RANK_WEIGHT))
    picks.append((ans["with"], 0.7))
    return picks


def recommend(model, places, ans, top_n=3):
    """1) 조건 필터(종류·날짜·지역·예산)는 코드로 거르고 2) 고른 보기와 소개글의 유사도를 가중 평균해 정렬한다.
    방문일(date)을 안 주면 오늘 날짜로 본다."""
    day = ans.get("date") or date.today().isoformat()
    candidates, excluded = [], []
    for p in places:
        ok, why = is_open(p, day)
        if ok and p["type"] not in ans["types"]:
            ok, why = False, "종류 불일치"
        if ok and ans.get("regions") and p["region"] not in ans["regions"]:
            ok, why = False, "지역 불일치"
        if ok and p["price"] is not None and p["price"] > ans["budget"]:  # 가격 미확인은 통과
            ok, why = False, "예산 초과"
        (candidates if ok else excluded).append(p if ok else (p["name"], why))
    if not candidates:  # 조건에 맞는 곳이 없으면 유사도 계산을 건너뛴다
        return [], excluded

    picks = answer_weights(ans)
    opts = model.encode([OPTION_TEXT[o] for o, _ in picks], convert_to_tensor=True)
    docs = model.encode([p["desc"] for p in candidates], convert_to_tensor=True)
    sims = util.cos_sim(opts, docs)  # [보기 수, 장소 수]

    total_w = sum(w for _, w in picks)
    ranked = []
    for j, p in enumerate(candidates):
        per_opt = [(o, w * sims[i][j].item()) for i, (o, w) in enumerate(picks)]
        score = sum(s for _, s in per_opt) / total_w
        best = max(per_opt, key=lambda x: x[1])[0]  # 추천 이유: 가장 크게 기여한 보기
        ranked.append((p, score, best))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:top_n], excluded


ANSWERS = [
    {"who": "사용자 A", "types": ["팝업", "전시", "카페"],
     "activity_rank": ["사진", "굿즈", "체험"], "mood_rank": ["귀여운", "트렌디", "레트로"],
     "with": "친구", "date": "2026-10-31", "regions": None, "budget": 10000},
    {"who": "사용자 B", "types": ["전시", "카페"],
     "activity_rank": ["관람", "음식", "사진"], "mood_rank": ["조용한", "예술적", "레트로"],
     "with": "혼자", "date": "2026-10-31", "regions": None, "budget": 30000},
]

if __name__ == "__main__":
    places = load_places()
    model = load_model()
    for ans in ANSWERS:
        top, excluded = recommend(model, places, ans)
        print(f"\n=== {ans['who']}: 종류 {ans['types']} / 하고 싶은 것 {ans['activity_rank']} / "
              f"분위기 {ans['mood_rank']} / {ans['with']} (방문일 {ans['date']}, 예산 {ans['budget']:,}원) ===")
        for i, (p, s, best) in enumerate(top, 1):
            price = "가격 미확인" if p["price"] is None else f"{p['price']:,}원"
            print(f"{i}. {p['name']} ({p['region']}, {price})  점수 {s:.2f}  이유: '{best}' 보기와 가장 잘 맞음")
        print("제외:", "; ".join(f"{n}({why})" for n, why in excluded))
