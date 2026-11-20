"""MoodMatch 추천 데모: 취향 질문지 답변(객관식)과 장소 소개글의 의미 유사도로 추천한다.

보기마다 설명 문장을 미리 정해 두고, 그 문장과 장소 소개글을 무료 로컬 임베딩 모델로 비교한다.
장소마다 태그를 붙일 필요가 없고 API 비용도 들지 않는다.

웹이 빨리 뜨도록 임베딩(문장 → 숫자 벡터)은 데이터를 받을 때 한 번만 계산해 vectors.npz에 저장해 둔다.
웹(app.py)은 이 파일만 읽으므로 AI 모델(PyTorch)을 불러오지 않는다.
  - 다시 계산: python demo/recommend.py --build  (fetch_places.py는 끝날 때 자동으로 실행)
"""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

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
LIKE_WEIGHT = 0.7  # 좋아요한 장소와 비슷한 정도를 보기 하나만큼 반영
DISLIKE_PENALTY = 0.3  # 별로예요한 장소와 많이 비슷하면 점수를 깎는다
PLACES_FILE = Path(__file__).with_name("places.json")  # fetch_places.py로 받은 실제 데이터
SAMPLE_FILE = Path(__file__).with_name("places_sample.json")  # 중간발표 때 쓴 테스트 데이터
VECS_FILE = Path(__file__).with_name("vectors.npz")  # 미리 계산한 임베딩 (문장 → 벡터)


def build_vectors():
    """보기 설명 문장과 장소 소개글(실제 + 테스트 데이터)을 임베딩해 vectors.npz로 저장한다.
    데이터를 새로 받았을 때만 실행하면 된다. 이때만 AI 모델이 필요하다."""
    from sentence_transformers import SentenceTransformer  # 무거워서 여기서만 불러온다

    texts = list(OPTION_TEXT.values())
    for path in (PLACES_FILE, SAMPLE_FILE):
        if path.exists():
            texts += [p["desc"] for p in json.loads(path.read_text(encoding="utf-8"))]
    texts = list(dict.fromkeys(texts))  # 중복 제거 (순서 유지)
    vecs = SentenceTransformer(MODEL).encode(texts, normalize_embeddings=True, show_progress_bar=False)
    np.savez_compressed(VECS_FILE, texts=np.array(texts), vecs=vecs.astype(np.float32))
    print(f"{VECS_FILE.name} 저장: 문장 {len(texts)}개")


def load_model():
    """미리 계산한 벡터 표를 읽는다 ({문장: 벡터}). 이름은 예전(AI 모델을 불러오던 때) 그대로 둔다."""
    if not VECS_FILE.exists():
        raise FileNotFoundError("vectors.npz가 없어요. 먼저 python demo/recommend.py --build 를 실행하세요.")
    data = np.load(VECS_FILE)
    return dict(zip(data["texts"].tolist(), data["vecs"]))


def encode(model, texts):
    """문장들의 벡터(길이 1로 맞춘 것)를 표에서 찾아 [문장 수, 차원] 배열로."""
    missing = [t[:30] for t in texts if t not in model]
    if missing:
        raise KeyError(f"벡터가 없는 문장 {len(missing)}개 (예: {missing[0]}…). "
                       "데이터가 바뀌었으면 python demo/recommend.py --build 를 실행하세요.")
    return np.stack([model[t] for t in texts])


def cos_sim(a, b):
    """코사인 유사도: 벡터 길이를 1로 맞춰 두었으니 내적과 같다. [a 개수, b 개수]"""
    return a @ b.T


def load_places(path=PLACES_FILE):
    """장소 데이터를 읽는다. 실제 데이터를 아직 안 받았으면 테스트 데이터를 쓴다."""
    path = Path(path) if Path(path).exists() else SAMPLE_FILE
    return json.loads(path.read_text(encoding="utf-8"))


def embed_places(model, places):
    """장소 소개글 벡터를 장소 순서대로 모아 둔다. 추천할 때마다 다시 찾지 않게."""
    return encode(model, [p["desc"] for p in places])


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


def recommend(model, places, ans, top_n=3, place_vecs=None, liked=(), disliked=(), diverse=True, exclude=()):
    """1) 조건 필터(종류·날짜·지역·예산)는 코드로 거르고 2) 고른 보기와 소개글의 유사도를 가중 평균해 정렬한다.
    diverse=True면 결과에 고른 종류·여러 지역이 섞이게 고른다(diversify).
    방문일(date)을 안 주면 오늘 날짜로 본다. place_vecs는 embed_places() 결과(없으면 여기서 계산).
    피드백: disliked(장소 id)는 빼고, liked(장소 id)와 소개글이 비슷한 곳은 점수를 더 주고,
    disliked와 비슷한 곳은 점수를 깎는다. exclude(장소 id)는 이미 본 곳이라 후보에서 뺀다(스와이프용)."""
    day = ans.get("date") or date.today().isoformat()
    if place_vecs is None:
        place_vecs = embed_places(model, places)
    candidates, excluded = [], []
    for p in places:
        ok, why = is_open(p, day)
        if ok and p["id"] in disliked:
            ok, why = False, "별로예요 표시"
        if ok and p["id"] in exclude:
            ok, why = False, "이미 본 곳"
        if ok and p["type"] not in ans["types"]:
            ok, why = False, "종류 불일치"
        if ok and ans.get("regions") and p["region"] not in ans["regions"]:
            ok, why = False, "지역 불일치"
        if ok and p["price"] is not None and p["price"] > ans["budget"]:  # 가격 미확인은 통과
            ok, why = False, "예산 초과"
        (candidates if ok else excluded).append(p if ok else (p["name"], why))
    if not candidates:  # 조건에 맞는 곳이 없으면 유사도 계산을 건너뛴다
        return [], excluded

    index = {id(p): i for i, p in enumerate(places)}
    docs = place_vecs[[index[id(p)] for p in candidates]]
    picks = answer_weights(ans)
    opts = encode(model, [OPTION_TEXT[o] for o, _ in picks])
    sims = cos_sim(opts, docs)  # [보기 수, 장소 수]
    liked_places = [(p, i) for i, p in enumerate(places) if p["id"] in liked]
    like_sims = cos_sim(place_vecs[[i for _, i in liked_places]], docs) if liked_places else None
    disliked_idx = [i for i, p in enumerate(places) if p["id"] in disliked]
    dis_sims = cos_sim(place_vecs[disliked_idx], docs) if disliked_idx else None

    ranked = []
    for j, p in enumerate(candidates):
        per_opt = [(o, w, w * float(sims[i, j])) for i, (o, w) in enumerate(picks)]
        per_opt += [(f"좋아요: {lp['name']}", LIKE_WEIGHT, LIKE_WEIGHT * float(like_sims[k, j]))
                    for k, (lp, _) in enumerate(liked_places) if lp["id"] != p["id"]]
        score = sum(s for _, _, s in per_opt) / sum(w for _, w, _ in per_opt)
        if dis_sims is not None:  # 별로예요한 곳 중 가장 비슷한 곳만큼 감점
            score -= DISLIKE_PENALTY * float(dis_sims[:, j].max())
        best = max(per_opt, key=lambda x: x[2])[0]  # 추천 이유: 가장 크게 기여한 보기
        ranked.append((p, score, best))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return (diversify(ranked, top_n) if diverse else ranked[:top_n]), excluded


def taste_profile(model, places, place_vecs, liked, disliked, options):
    """찜·별로예요 반응으로 알아낸 취향: 보기마다 (찜한 곳과의 유사도 - 전체 평균)을 계산해 높은 순으로.
    별로예요한 곳과 비슷한 보기는 점수를 낮춘다. 찜한 곳이 없으면 빈 목록."""
    idx = {p["id"]: i for i, p in enumerate(places)}
    li = [idx[i] for i in liked if i in idx]
    di = [idx[i] for i in disliked if i in idx]
    if not li:
        return []
    opts = encode(model, [OPTION_TEXT[o] for o in options])
    base = cos_sim(opts, place_vecs).mean(axis=1)  # 보기마다 모든 장소와의 평균 유사도(기준선)
    pref = cos_sim(opts, place_vecs[li]).mean(axis=1) - base
    if di:
        pref = pref - 0.5 * (cos_sim(opts, place_vecs[di]).mean(axis=1) - base)
    return sorted(zip(options, pref.tolist()), key=lambda x: -x[1])


def diversify(ranked, top_n):
    """한 종류·한 지역만 몰리지 않게, 덜 나온 종류 > 아직 안 나온 지역 > 점수 순으로 하나씩 고른다."""
    picked, rest = [], list(ranked)
    while rest and len(picked) < top_n:
        types = [p["type"] for p, _, _ in picked]
        regions = {p["region"] for p, _, _ in picked}
        pick = max(rest, key=lambda x: (-types.count(x[0]["type"]), x[0]["region"] not in regions, x[1]))
        rest.remove(pick)
        picked.append(pick)
    return picked


ANSWERS = [
    {"who": "사용자 A", "types": ["팝업", "전시", "카페"],
     "activity_rank": ["사진", "굿즈", "체험"], "mood_rank": ["귀여운", "트렌디", "레트로"],
     "with": "친구", "date": "2026-10-31", "regions": None, "budget": 10000},
    {"who": "사용자 B", "types": ["전시", "카페"],
     "activity_rank": ["관람", "음식", "사진"], "mood_rank": ["조용한", "예술적", "레트로"],
     "with": "혼자", "date": "2026-10-31", "regions": None, "budget": 30000},
]

if __name__ == "__main__":
    if "--build" in sys.argv:
        build_vectors()
        sys.exit()
    places = load_places(SAMPLE_FILE)  # 예시 답변의 방문일(10/31)에 맞춘 테스트 데이터
    model = load_model()
    for ans in ANSWERS:
        top, excluded = recommend(model, places, ans, diverse=False)  # 중간발표 결과(점수순) 그대로 재현
        print(f"\n=== {ans['who']}: 종류 {ans['types']} / 하고 싶은 것 {ans['activity_rank']} / "
              f"분위기 {ans['mood_rank']} / {ans['with']} (방문일 {ans['date']}, 예산 {ans['budget']:,}원) ===")
        for i, (p, s, best) in enumerate(top, 1):
            price = "가격 미확인" if p["price"] is None else f"{p['price']:,}원"
            print(f"{i}. {p['name']} ({p['region']}, {price})  점수 {s:.2f}  이유: '{best}' 보기와 가장 잘 맞음")
        print("제외:", "; ".join(f"{n}({why})" for n, why in excluded))
