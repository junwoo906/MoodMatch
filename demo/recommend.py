import json
import sys
from pathlib import Path

from tags import PRICE_LABEL, build_profile

sys.stdout.reconfigure(encoding="utf-8")

WEIGHTS = {"activity": 0.4, "mood": 0.3, "type": 0.15, "price": 0.15}


def passes_filter(place, profile):
    """조건 필터: 하나라도 맞지 않으면 추천 후보에서 제외한다. (제외 사유를 함께 반환)"""
    if place["status"] != "운영중":
        return False, "운영 종료"
    day = profile["visit_date"]
    if place["start"] and day < place["start"]:
        return False, "방문일에 아직 시작 전"
    if place["end"] and day > place["end"]:
        return False, "방문일에 이미 종료"
    if profile["regions"] and place["region"] not in profile["regions"]:
        return False, "지역 불일치"
    if place["price"] > profile["max_price"]:
        return False, "가격 초과"
    return True, ""


def match(prefs, place_tags):
    """사용자가 중요하게 여기는 태그를 장소가 얼마나 갖추고 있는지 (0~1)"""
    total = sum(prefs.values())
    hit = sum(prefs[t] for t in place_tags if t in prefs)
    return hit / total if total else 0.0


def score(place, profile):
    parts = {
        "activity": match(profile["activity"], place["activities"]),
        "mood": match(profile["mood"], place["moods"]),
        "type": 1.0 if place["type"] in profile["types"] else 0.0,
        "price": 1 - 0.25 * place["price"],
    }
    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    matched = [t for t in place["activities"] if profile["activity"][t] > 0] + \
              [t for t in place["moods"] if profile["mood"][t] > 0]
    return round(total, 3), matched


def recommend(places, profile, top_n=3):
    ranked, excluded = [], []
    for p in places:
        ok, reason = passes_filter(p, profile)
        if not ok:
            excluded.append((p["name"], reason))
            continue
        s, matched = score(p, profile)
        ranked.append({"name": p["name"], "score": s, "matched": matched,
                       "region": p["region"], "price": PRICE_LABEL[p["price"]]})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:top_n], excluded


USERS = {
    "사용자 A (체험·사진·귀여운·무료 선호)": {
        "activity_rank": ["체험", "사진", "굿즈"], "mood_rank": ["귀여운", "트렌디"],
        "types": ["팝업"], "max_price": 1, "regions": None, "visit_date": "2026-10-31",
    },
    "사용자 B (관람·조용한·예술적 선호)": {
        "activity_rank": ["관람", "사진"], "mood_rank": ["예술적", "조용한"],
        "types": ["전시", "카페"], "max_price": 2, "regions": None, "visit_date": "2026-10-31",
    },
}

if __name__ == "__main__":
    places = json.loads(Path(__file__).with_name("places.json").read_text(encoding="utf-8"))
    for label, answers in USERS.items():
        top, excluded = recommend(places, build_profile(answers))
        print(f"\n=== {label} / 방문일 {answers['visit_date']} ===")
        for i, r in enumerate(top, 1):
            print(f"{i}. {r['name']} ({r['region']}, {r['price']})  점수 {r['score']}  일치 태그: {', '.join(r['matched']) or '-'}")
        print("제외:", "; ".join(f"{n}({why})" for n, why in excluded))
