"""공식 공개 데이터에서 장소를 받아 places.json을 새로 만든다. 필요할 때 직접 실행한다.

- 전시: 서울 열린데이터광장 「서울시 문화행사 정보」 (분류 '전시/미술')
  API에 소개글이 비어 있으면 서울문화포털 상세 페이지(robots.txt 허용 경로)에서 소개글을 가져온다.
- 팝업: 같은 API에서 제목에 '팝업'이 들어간 행사
        + 롯데월드몰 공식 사이트 행사 목록(robots.txt 전체 허용, '팝업'·'엔터테인먼트' 분류만)
        + 네이버 검색 API(뉴스, NAVER API HUB)에서 팝업 오픈 기사를 찾아 이름·기간·지역을 뽑는다 (기간을 못 뽑은 기사는 버림)
- 카페: 한국관광공사 TourAPI (KorService2)

API 키는 프로젝트 폴더의 .env 파일에 넣는다 (git에 올라가지 않음).
    SEOUL_API_KEY=...   (없으면 테스트용 'sample' 키로 5건만 받음)
    TOUR_API_KEY=...    (없으면 카페는 건너뜀)
    NAVER_CLIENT_ID=... / NAVER_CLIENT_SECRET=...   (없으면 뉴스 팝업은 건너뜀)

실행: python demo/fetch_places.py
"""
import html
import json
import os
import re
import sys
import time
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
PORTAL_URL = "https://culture.seoul.go.kr/culture/culture/cultureEvent/view.do?cultcode={}&menuNo=200008"

TOUR_URL = "https://apis.data.go.kr/B551011/KorService2"
TOUR_COMMON = {"MobileOS": "ETC", "MobileApp": "MoodMatch", "_type": "json"}
SEOUL_REGION = "11"            # 법정동 시도 코드: 서울
CAFE_CATEGORY = ("FD", "FD05")  # 분류체계 대/중분류: 음식 > 카페/찻집 (lclsSystmCode2로 확인함)
CAFE_LIMIT = 40                # 카페는 소개글을 한 곳씩 따로 받아야 해서 개수를 제한 (하루 호출 한도 고려)

LWT_URL = "https://www.lwt.co.kr/api/event/list?lang=KO&pageNum=1&pageRow=100&type="
LWT_TYPE = {"POP_UP": "팝업", "ENTERTAINMENT": "전시"}  # 할인·매장 이벤트는 제외

# 2026-07-31부터 검색 API 새 키는 네이버 클라우드 NAVER API HUB에서만 발급 (응답 형식은 키 발급 후 확인)
NAVER_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
# 비용 안전장치: 네이버 검색 API 무료 한도(월 775,000건, 일 25,000건)보다 훨씬 낮게 잡고,
# 호출할 때마다 횟수를 파일에 기록해 이 선을 넘으면 더 부르지 않는다. 절대 유료 구간에 가지 않게.
NAVER_DAILY_LIMIT = 20000    # 무료 일 한도(25,000)의 80%
NAVER_MONTHLY_LIMIT = 700000 # 무료 월 한도(775,000)의 약 90% (콘솔 한도 설정과 같게)
USAGE_FILE = Path(__file__).with_name(".api_usage.json")  # git에 올라가지 않음
NAVER_QUERIES = ["팝업스토어 오픈", "성수 팝업스토어", "더현대 서울 팝업", "홍대 팝업스토어", "잠실 팝업스토어"]
# 기사에 나온 장소 이름 → 구 (서울이 아닌 곳은 버린다)
PLACE_GU = {
    "성수": "성동구", "서울숲": "성동구", "더현대": "영등포구", "여의도": "영등포구", "IFC몰": "영등포구",
    "홍대": "마포구", "연남": "마포구", "합정": "마포구", "망원": "마포구", "잠실": "송파구", "롯데월드몰": "송파구",
    "코엑스": "강남구", "압구정": "강남구", "가로수길": "강남구", "신사": "강남구", "강남": "강남구", "청담": "강남구",
    "명동": "중구", "을지로": "중구", "DDP": "중구", "동대문": "중구", "신세계백화점 본점": "중구", "롯데백화점 본점": "중구",
    "용산": "용산구", "한남": "용산구", "이태원": "용산구", "삼청": "종로구", "인사동": "종로구", "익선": "종로구",
    "신촌": "서대문구", "타임스퀘어": "영등포구", "영등포": "영등포구",
}


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


def portal_desc(cultcode):
    """서울문화포털 행사 상세 페이지에서 '상세보기' 아래 소개글을 가져온다."""
    time.sleep(0.5)  # 서버에 부담을 주지 않게 천천히
    try:
        page = requests.get(PORTAL_URL.format(cultcode), timeout=20).text
    except requests.RequestException:
        return ""
    text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", page, flags=re.S)
    text = " ".join(html.unescape(text).split())
    _, found, after = text.partition("상세보기")
    return after[:300] if found else ""


def from_seoul(row, kind):
    start, end = row["STRTDATE"][:10], row["END_DATE"][:10]
    cult = re.search(r"cultcode=(\d+)", row["HMPG_ADDR"])
    desc = " ".join(t for t in (row["PROGRAM"], row["ETC_DESC"]) if t.strip())
    if len(desc) < 50 and cult and end >= TODAY:  # API 소개글이 비어 있는 경우가 많아 포털에서 보충
        desc = portal_desc(cult.group(1)) or desc
    if len(desc) < 20:  # 그래도 없으면 제목·장소로 대신
        desc = f"{row['TITLE']}. {row['PLACE']}에서 열리는 {row['CODENAME']} 행사. {desc}".strip()
    desc = f"{row['TITLE']}. {desc}" if row["TITLE"] not in desc else desc
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


def fetch_lwt():
    """롯데월드몰 행사 목록(JSON)에서 팝업과 전시성 행사를 가져온다."""
    try:
        items = requests.get(LWT_URL, timeout=20).json()
    except (requests.RequestException, ValueError):
        print("롯데월드몰 행사 목록을 받지 못했습니다.")
        return []
    places = []
    for it in items:
        name = it["eventNm"]["ko"].strip()
        if it["type"] not in LWT_TYPE or re.search(r"외국인|Foreign", name):
            continue
        body = clean((it.get("content") or {}).get("ko") or "")
        loc = (it.get("loc") or "롯데월드몰").strip()
        places.append({
            "id": f"lwt-{it['seq']}",
            "name": name,
            "type": LWT_TYPE[it["type"]],
            "region": "송파구",
            "start": it["startDate"].replace(".", "-"),
            "end": it["endDate"].replace(".", "-"),
            "price": None,
            "desc": f"{name}. {loc}에서 열리는 행사. {body}"[:300],
            "place": loc,
            "source": "https://www.lwt.co.kr",
        })
    return places


def clean(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).split())


def news_period(text, pub):
    """기사 글에서 운영 기간을 뽑는다. '11월 20일부터 12월 7일까지', '21일부터 다음달 3일까지',
    '11월 26일~2027년 1월 4일', '12월 7일까지' 등. 시작일이 없으면 기사 날짜(pub)부터로 본다.
    연도가 없으면 기사 연도로 정하고, 기사보다 두 달 이상 이른 달이면 다음 해로 본다. 못 찾으면 None."""
    if re.search(r"지난\s?달|지난\s*\d{1,2}월", text):  # 이미 지난 행사 이야기
        return None
    day = r"(?:(\d{4})년\s*)?(?:(\d{1,2})월|(다음\s?달|내달))?\s*(\d{1,2})일"
    m = re.search(day + r"\s*(?:부터|~|-|–)\s*" + day + r"(?:\s*까지)?", text)
    if m:
        start_g, end_g = m.groups()[:4], m.groups()[4:]
    else:
        m = re.search(day + r"\s*까지", text)
        if not m or not (m.group(2) or m.group(3)):  # '7일까지'처럼 달이 없으면 믿기 어려워 버림
            return None
        start_g, end_g = None, m.groups()

    def to_date(g, base_month):
        y, mon, next_month, d = g
        mon = int(mon) if mon else (pub.month % 12 + 1 if next_month else base_month)
        y = int(y) if y else pub.year + (1 if mon < pub.month - 1 else 0)
        return date(y, mon, int(d))

    try:
        start = to_date(start_g, pub.month) if start_g else pub
        end = to_date(end_g, start.month)
    except ValueError:
        return None
    if end < start and not end_g[0]:  # '12월 20일~1월 15일': 해를 넘김
        end = end.replace(year=end.year + 1)
    if not start <= end or (start - pub).days > 90:  # 석 달 넘게 뒤에 시작한다는 건 연도를 잘못 읽었을 가능성
        return None
    return start.isoformat(), end.isoformat()


STOP_WORDS = {"팝업", "팝업스토어", "스토어", "서울", "오픈", "운영", "진행", "선보여", "선보인다", "개최", "오는",
              "까지", "부터", "에서", "있다", "한다", "이번", "브랜드", "매장", "공식", "기념"}


def words(text):
    return {w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", text)} - STOP_WORDS


def same_popup(a, b):
    """같은 지역에 기간이 겹치고, 기사 낱말이 충분히 겹치면 같은 팝업을 다룬 다른 기사로 본다."""
    if a["region"] != b["region"] or a["end"] < b["start"] or b["end"] < a["start"]:
        return False
    wa, wb = words(a["desc"]), words(b["desc"])
    return len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.3


def news_name(title):
    """기사 제목에서 팝업 이름: 따옴표 안 이름이 있으면 그것, 없으면 제목 그대로."""
    m = re.search(r"['‘\"“]([^'’\"”]{2,30})['’\"”]", title)
    name = m.group(1) if m else title
    return name if "팝업" in name else f"{name} 팝업"


def news_gu(text):
    for place, g in PLACE_GU.items():
        if place in text:
            return g
    return None


def naver_call_allowed():
    """오늘·이번 달 네이버 호출 횟수를 확인하고, 한도 안이면 1회를 기록하고 True."""
    usage = json.loads(USAGE_FILE.read_text(encoding="utf-8")) if USAGE_FILE.exists() else {}
    day, month = TODAY, TODAY[:7]
    used_day = usage.get("day", {}).get(day, 0)
    used_month = usage.get("month", {}).get(month, 0)
    if used_day >= NAVER_DAILY_LIMIT or used_month >= NAVER_MONTHLY_LIMIT:
        print(f"네이버 호출 안전 한도 도달 (오늘 {used_day}/{NAVER_DAILY_LIMIT}, 이번 달 {used_month}/{NAVER_MONTHLY_LIMIT}) → 더 부르지 않습니다.")
        return False
    usage["day"] = {day: used_day + 1}  # 오늘 것만 남긴다
    usage["month"] = {**usage.get("month", {}), month: used_month + 1}
    USAGE_FILE.write_text(json.dumps(usage), encoding="utf-8")
    return True


def fetch_news_popups(cid, secret):
    headers = {"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret}
    popups = []
    for q in NAVER_QUERIES:
        if not naver_call_allowed():
            break
        r = requests.get(NAVER_URL, headers=headers, params={"query": q, "display": 100, "sort": "date"}, timeout=20)
        for it in r.json().get("items", []):
            title, body = clean(it["title"]), clean(it["description"])
            if "팝업" not in title or re.search(r"성료|마무리|종료|막\s?내려", title):
                continue
            pub = date(*time.strptime(it["pubDate"][5:16], "%d %b %Y")[:3])
            period, region = news_period(body + " " + title, pub), news_gu(title + " " + body)
            if not period or not region:  # 기간이나 서울 장소를 모르면 추천할 수 없어서 버린다
                continue
            name = news_name(title)
            item = {
                "id": f"news-{name}",
                "name": name,
                "type": "팝업",
                "region": region,
                "start": period[0],
                "end": period[1],
                "price": None,
                "desc": f"{title}. {body}",
                "place": "",
                "source": it["originallink"] or it["link"],
            }
            if not any(same_popup(item, p) for p in popups):  # 같은 팝업을 다룬 다른 기사는 버림
                popups.append(item)
    return popups


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
    naver = (os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET"))
    if seoul_key == "sample":
        print("SEOUL_API_KEY가 없어 테스트용 sample 키로 받습니다 (분류별 5건만).")

    exhibitions, popups = fetch_seoul(seoul_key)
    for p in fetch_lwt():
        (popups if p["type"] == "팝업" else exhibitions).append(p)
    if all(naver):
        popups += fetch_news_popups(*naver)
    else:
        print("NAVER_CLIENT_ID/SECRET이 없어 뉴스 팝업은 건너뜁니다.")
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
