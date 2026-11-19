"""공식 공개 데이터에서 장소를 받아 places.json을 새로 만든다. 필요할 때 직접 실행한다.

- 전시: 서울 열린데이터광장 「서울시 문화행사 정보」 (분류 '전시/미술')
- 팝업: 같은 API에서 제목에 '팝업'이 들어간 행사
- 카페: 한국관광공사 TourAPI (KorService2)

API 키는 프로젝트 폴더의 .env 파일에 넣는다 (git에 올라가지 않음).
    SEOUL_API_KEY=...   (없으면 테스트용 'sample' 키로 5건만 받음)
    TOUR_API_KEY=...    (없으면 카페는 건너뜀)

실행: python demo/fetch_places.py
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OUT_FILE = Path(__file__).with_name("places.json")
TODAY = date.today().isoformat()

SEOUL_URL = "http://openapi.seoul.go.kr:8088/{key}/json/culturalEventInfo/{start}/{end}/{code}/{title}"
SEOUL_PAGE = 1000  # 한 번에 받을 수 있는 최대 건수 (sample 키는 5건)

TOUR_URL = "https://apis.data.go.kr/B551011/KorService2"
TOUR_COMMON = {"MobileOS": "ETC", "MobileApp": "MoodMatch", "_type": "json"}
SEOUL_REGION = "11"            # 법정동 시도 코드: 서울
CAFE_CATEGORY = ("FD", "FD05")  # 분류체계 대/중분류: 음식 > 카페·찻집 (키 발급 후 lclsSystmCode2로 확인 필요)
CAFE_LIMIT = 40                # 카페는 소개글을 한 곳씩 따로 받아야 해서 개수를 제한 (하루 호출 한도 고려)


def won(text):
    """'성인 15,000원 / 청소년 10,000원' 같은 요금 글에서 가장 싼 금액. 못 찾으면 None(가격 미확인)."""
    nums = [int(n.replace(",", "")) for n in re.findall(r"(\d[\d,]*)\s*원", text or "")]
    return min(nums) if nums else None


def gu(addr):
    """주소에서 'OO구'를 뽑는다."""
    m = re.search(r"(\S+구)\b", addr or "")
    return m.group(1) if m else "서울"


def seoul_events(key, code=" ", title=" "):
    """서울시 문화행사 API를 끝까지 넘겨 가며 받는다."""
    rows, start = [], 1
    page = 5 if key == "sample" else SEOUL_PAGE
    while True:
        url = SEOUL_URL.format(key=key, start=start, end=start + page - 1,
                               code=quote(code, safe=""), title=quote(title, safe=""))
        data = requests.get(url, timeout=30).json().get("culturalEventInfo")
        if not data:  # 결과 없음(INFO-200) 등
            break
        rows += data["row"]
        start += page
        if key == "sample" or start > data["list_total_count"]:
            break
    return rows


def from_seoul(row, kind):
    start, end = row["STRTDATE"][:10], row["END_DATE"][:10]
    desc = " ".join(t for t in (row["PROGRAM"], row["ETC_DESC"]) if t.strip())
    if len(desc) < 20:  # 소개글이 비어 있는 경우가 많아 제목·장소로 보충
        desc = f"{row['TITLE']}. {row['PLACE']}에서 열리는 {row['CODENAME']} 행사. {desc}".strip()
    cult = re.search(r"cultcode=(\d+)", row["HMPG_ADDR"])
    return {
        "id": f"seoul-{cult.group(1) if cult else row['TITLE']}",
        "name": row["TITLE"],
        "type": kind,
        "region": row["GUNAME"] or gu(row["PLACE"]),
        "start": start,
        "end": end,
        "price": 0 if row["IS_FREE"] == "무료" else won(row["USE_FEE"]),
        "desc": desc,
        "place": row["PLACE"],
        "source": row["ORG_LINK"] or row["HMPG_ADDR"],
    }


def fetch_seoul(key):
    exhibitions = [from_seoul(r, "전시") for r in seoul_events(key, code="전시/미술")]
    popups = [from_seoul(r, "팝업") for r in seoul_events(key, title="팝업")
              if r["CODENAME"] not in ("교육/체험",)]  # '팝업북 만들기' 같은 수업은 제외
    return exhibitions, popups


def tour(op, key, **params):
    r = requests.get(f"{TOUR_URL}/{op}", params={"serviceKey": key, **TOUR_COMMON, **params}, timeout=30)
    body = r.json()["response"]["body"]
    items = body["items"]["item"] if body.get("items") else []
    return items if isinstance(items, list) else [items]


def fetch_cafes(key):
    big, mid = CAFE_CATEGORY
    items = tour("areaBasedList2", key, lDongRegnCd=SEOUL_REGION, lclsSystm1=big, lclsSystm2=mid,
                 arrange="Q", numOfRows=CAFE_LIMIT, pageNo=1)  # Q: 수정일순(최근 정보 우선)
    cafes = []
    for it in items:
        detail = tour("detailCommon2", key, contentId=it["contentid"])
        overview = re.sub(r"<[^>]+>", " ", detail[0].get("overview", "")) if detail else ""
        if len(overview.strip()) < 20:  # 소개글이 없으면 분위기를 알 수 없어 제외
            continue
        cafes.append({
            "id": f"tour-{it['contentid']}",
            "name": it["title"],
            "type": "카페",
            "region": gu(it["addr1"]),
            "start": None,
            "end": None,
            "price": None,
            "desc": " ".join(overview.split())[:300],
            "place": it["addr1"],
            "source": f"https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid={it['contentid']}",
        })
    return cafes


def main():
    seoul_key = os.getenv("SEOUL_API_KEY") or "sample"
    tour_key = os.getenv("TOUR_API_KEY")
    if seoul_key == "sample":
        print("SEOUL_API_KEY가 없어 테스트용 sample 키로 받습니다 (분류별 5건만).")

    exhibitions, popups = fetch_seoul(seoul_key)
    cafes = fetch_cafes(tour_key) if tour_key else []
    if not tour_key:
        print("TOUR_API_KEY가 없어 카페는 건너뜁니다.")

    places, seen = [], set()
    for p in exhibitions + popups + cafes:
        if p["id"] in seen or (p["end"] and p["end"] < TODAY) or (p["end"] and p["start"] > p["end"]):
            continue  # 중복, 이미 끝난 곳, 기간이 잘못된 데이터 제외
        seen.add(p["id"])
        places.append(p)

    OUT_FILE.write_text(json.dumps(places, ensure_ascii=False, indent=2), encoding="utf-8")
    count = {t: sum(p["type"] == t for p in places) for t in ("전시", "팝업", "카페")}
    print(f"{OUT_FILE.name} 저장: 총 {len(places)}곳 {count} (기준일 {TODAY})")


if __name__ == "__main__":
    main()
