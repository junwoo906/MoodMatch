"""MoodMatch 웹: 취향 질문지 5문항에 답하면 지금 갈 수 있는 팝업·전시·카페 Top 6를 추천한다.
추천 결과 · 지도 · 찜한 곳으로 짜는 하루 코스를 골라 볼 수 있다.

실행: streamlit run demo/app.py
"""
import json
from datetime import date
from html import escape
from itertools import permutations
from math import asin, cos, radians, sin, sqrt

import streamlit as st

import recommend as rec

TYPES = ["팝업", "전시", "카페"]
ACTIVITIES = ["체험", "사진", "굿즈", "관람", "음식"]
MOODS = ["귀여운", "조용한", "트렌디", "예술적", "레트로"]
COMPANIONS = ["혼자", "친구", "연인", "가족"]
BUDGETS = {"무료만": 0, "5천 원": 5000, "1만 원": 10000, "2만 원": 20000, "3만 원": 30000, "상관없음": 10**9}
TYPE_ICON = {"팝업": "🛍️", "전시": "🖼️", "카페": "☕"}
TYPE_COLOR = {"팝업": "#FF3B30", "전시": "#AF52DE", "카페": "#FF9500"}  # 지도 핀 색
DESC_LEN = 110  # 카드에 보일 소개글 길이
TOP_N = 6       # 추천 개수 (2열로 3줄)
SOON_DAYS = 7   # 끝나기 7일 전부터 '곧 끝나요', 연 지 7일 안이면 'NEW'
BROWSE_PAGE = 12  # 전체 둘러보기에서 한 번에 보여 줄 개수

# 취향 유형 = 1순위 분위기(형용사) + 1순위 하고 싶은 것(명사)
TASTE_MOOD = {
    "귀여운": ("💗", "러블리", "귀엽고 사랑스러운 것에 마음이 끌리는"),
    "조용한": ("🌿", "힐링", "북적임보다 여유와 고요함을 즐기는"),
    "트렌디": ("⚡", "트렌디", "요즘 뜨는 곳은 꼭 먼저 가 보는"),
    "예술적": ("🎨", "감성 아트", "작품과 공간의 분위기에 빠져드는"),
    "레트로": ("📼", "레트로", "옛 감성과 아날로그를 사랑하는"),
}
TASTE_ACT = {"체험": "모험가", "사진": "포토그래퍼", "굿즈": "컬렉터", "관람": "감상가", "음식": "미식가"}

CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
:root { --ink: #1D1D1F; --gray: #6E6E73; --line: #E5E5EA; --fill: #F5F5F7; --blue: #0071E3; }
html, body, [class*="st-"], button, input, textarea {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Apple SD Gothic Neo", Pretendard, sans-serif;
  -webkit-font-smoothing: antialiased; letter-spacing: -0.01em; }
.block-container { padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1180px; }
header[data-testid="stHeader"] { background: rgba(245,245,247,.72); backdrop-filter: saturate(180%) blur(20px); }

/* 첫 화면 큰 제목 */
.hero { text-align: center; padding: 34px 16px 30px; }
.hero .eyebrow { color: var(--blue); font-weight: 600; font-size: 1.05rem; margin-bottom: 6px; }
.hero h1 { font-size: 3.4rem; font-weight: 700; letter-spacing: -0.035em; line-height: 1.08; margin: 0; padding: 0;
           color: var(--ink); }
.hero h1 span { background: linear-gradient(90deg, #0071E3, #7C5CFF 50%, #FF375F);
                -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero p { color: var(--gray); font-size: 1.25rem; margin: 14px 0 0; letter-spacing: -0.015em; }
.section { font-weight: 700; font-size: 1.35rem; letter-spacing: -0.02em; margin: 2px 0 12px; color: var(--ink); }
.section small { color: var(--gray); font-weight: 500; font-size: .9rem; }

/* 흰 카드 (질문지, 장소 카드) */
div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {
  background: #fff; border-radius: 22px; border: none !important;
  box-shadow: 0 2px 12px rgba(0,0,0,.06); transition: transform .25s ease, box-shadow .25s ease; }
div[data-testid="stVerticalBlockBorderWrapper"]:hover { transform: translateY(-3px); box-shadow: 0 10px 30px rgba(0,0,0,.10); }
div[data-testid="stForm"] { padding: 26px 24px; }

/* 버튼: 알약 모양, 주 버튼은 애플 파랑 */
.stButton button, .stFormSubmitButton button {
  border-radius: 980px; border: none; background: var(--fill); color: var(--ink); font-weight: 600; transition: all .2s; }
.stButton button:hover { background: #E8E8ED; color: var(--ink); }
.stFormSubmitButton button, .stButton button[kind="primary"] { background: var(--blue); color: #fff; padding: 10px 0; }
.stFormSubmitButton button:hover { background: #0077ED; color: #fff; }

/* 보기 선택: 애플식 세그먼트 버튼 */
.st-key-view [role="radiogroup"] { background: #E8E8ED; border-radius: 980px; padding: 4px; gap: 2px;
  display: flex; flex-wrap: nowrap; width: fit-content; max-width: 100%; overflow-x: auto; scrollbar-width: none;
  margin-bottom: 14px; }
.st-key-view [role="radiogroup"] > div { margin: 0 !important; flex: 0 0 auto; }
.st-key-view [data-testid="stRadioOption"] { border-radius: 980px; padding: 7px 15px; margin: 0 !important;
  cursor: pointer; transition: background .2s, box-shadow .2s; white-space: nowrap; }
.st-key-view [data-testid="stRadioOption"]:hover { background: rgba(255,255,255,.55); }
/* 라디오 동그라미 숨기기 (글자만 남김) */
.st-key-view [data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) { display: none; }
.st-key-view [data-testid="stRadioOption"][data-selected="true"] { background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.12); }
.st-key-view [data-testid="stRadioOption"] p { font-weight: 600; font-size: .9rem; color: var(--ink); margin: 0; }
.st-key-view [data-testid="stRadioOption"]:not([data-selected="true"]) p { color: #424245; }

/* 나의 취향 유형: 검은 타일 */
.taste { background: #1D1D1F; color: #F5F5F7; border-radius: 22px; padding: 22px 26px; margin-bottom: 16px;
         display: flex; align-items: center; gap: 18px; }
.taste .emoji { font-size: 46px; }
.taste small { color: #A1A1A6; font-weight: 600; letter-spacing: .02em; }
.taste b { font-size: 1.6rem; letter-spacing: -0.025em;
           background: linear-gradient(90deg, #2997FF, #A78BFA 55%, #FF6482);
           -webkit-background-clip: text; background-clip: text; color: transparent; }

.thumb { width: 100%; height: 200px; object-fit: cover; border-radius: 16px; display: block; }
.noimg { height: 200px; border-radius: 16px; display: flex; align-items: center; justify-content: center;
         font-size: 64px; background: linear-gradient(135deg, #F5F5F7, #E8E8ED); }
.thumb.mini, .noimg.mini { height: 140px; font-size: 44px; }
.mtitle { font-weight: 600; font-size: .98rem; line-height: 1.35; margin: 10px 0 6px; height: 2.7em; overflow: hidden;
          display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; color: var(--ink); }
.title { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.3; margin: 12px 0 8px; color: var(--ink); }
.rank { display: inline-block; background: var(--ink); color: #fff; border-radius: 999px;
        width: 26px; height: 26px; line-height: 26px; text-align: center; font-size: .82rem; margin-right: 8px;
        vertical-align: 2px; }
.chip { display: inline-block; padding: 3px 10px; margin: 0 4px 4px 0; border-radius: 999px;
        background: var(--fill); color: #424245; font-size: .78rem; font-weight: 500; }
.chip.soon { background: #FFE5E3; color: #D70015; font-weight: 600; }
.chip.new { background: #E3F0FF; color: var(--blue); font-weight: 600; }
.reason { background: var(--fill); border-radius: 12px; padding: 9px 12px; margin: 8px 0; font-size: .9rem; color: var(--ink); }
.reason small { color: var(--gray); }
.desc { color: var(--gray); font-size: .88rem; line-height: 1.55; margin: 4px 0; }
.desc a { color: var(--blue); font-weight: 500; text-decoration: none; }
.desc a:hover { text-decoration: underline; }
.step { display: flex; gap: 12px; align-items: center; }
.step .num { background: var(--blue); color: #fff; border-radius: 999px; min-width: 30px; height: 30px;
             line-height: 30px; text-align: center; font-weight: 600; }
.move { color: var(--gray); font-size: .85rem; margin: 2px 0 2px 42px; }
.empty { text-align: center; color: var(--gray); padding: 70px 20px; font-size: 1.02rem; line-height: 1.7; }
.empty div { font-size: 52px; margin-bottom: 8px; }
.swstat { display: flex; gap: 12px; margin-bottom: 16px; }
.swstat div { flex: 1; background: #fff; border-radius: 16px; padding: 12px 16px; box-shadow: 0 2px 12px rgba(0,0,0,.06); }
.swstat b { font-size: 1.6rem; display: block; letter-spacing: -0.02em; }
.swstat small { color: var(--gray); }
.tlabel { color: var(--gray); font-size: .85rem; font-weight: 600; margin: 10px 0 6px; }
.tbar { display: flex; align-items: center; gap: 10px; margin: 6px 0; font-size: .92rem; }
.tbar span { width: 52px; color: var(--ink); font-weight: 600; }
.tbar i { height: 10px; border-radius: 999px; display: block; transition: width .4s; }
@media (max-width: 640px) { .hero h1 { font-size: 2.3rem; } .hero p { font-size: 1.05rem; }
  .st-key-view [role="radiogroup"] { flex-wrap: wrap; border-radius: 20px; } }
</style>
"""


@st.cache_resource(show_spinner="추천 데이터를 불러오는 중…")
def load_data(version):
    """미리 계산한 벡터 표와 장소 데이터를 읽는다. AI 모델은 불러오지 않아서 금방 뜬다.
    version(데이터 파일 수정 시각)이 바뀌면 = 데이터를 새로 받으면 다시 읽는다."""
    model = rec.load_model()
    places = rec.load_places()
    return model, places, rec.embed_places(model, places)


def reason_text(best):
    """추천 이유(가장 크게 기여한 보기)를 문장으로"""
    if best.startswith("좋아요: "):
        return f"찜한 ‘{best[5:]}’와 비슷해요"
    if best in ACTIVITIES:
        return f"‘{best}’ 하고 싶은 마음과 가장 잘 맞아요"
    if best in MOODS:
        return f"‘{best}’ 분위기와 가장 잘 맞아요"
    return f"{best} 가기 좋은 곳이에요"


def period_text(p):
    if not p["start"] and not p["end"]:
        return "상설"
    return f"{p['start'] or ''} ~ {p['end'] or ''}"


def badge(p, day):
    """방문일 기준 '곧 끝나요'(끝나기 7일 이내) 또는 'NEW'(연 지 7일 이내) 배지. 없으면 None."""
    if p["end"]:
        left = (date.fromisoformat(p["end"]) - day).days
        if 0 <= left <= SOON_DAYS:
            return ("⏰ 오늘 마감" if left == 0 else f"⏰ D-{left} 곧 끝나요"), "soon"
    if p["start"] and 0 <= (day - date.fromisoformat(p["start"])).days <= SOON_DAYS:
        return "✨ NEW 새로 오픈", "new"
    return None


def taste_card(ans):
    emoji, adj, line = TASTE_MOOD[ans["mood_rank"][0]]
    noun = TASTE_ACT[ans["activity_rank"][0]]
    st.markdown(f'<div class="taste"><span class="emoji">{emoji}</span><div><small>나의 취향 유형</small><br>'
                f'<b>{adj} {noun}</b><br>{line} {noun} 타입이에요. '
                f'{ans["with"]} 가기 좋은 곳으로 골라 봤어요.</div></div>', unsafe_allow_html=True)


def km(a, b):
    """두 장소 사이 직선거리(km). 좌표가 없는 곳이 끼면 0으로 본다."""
    if a.get("lat") is None or b.get("lat") is None:
        return 0.0
    lat1, lon1, lat2, lon2 = map(radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def plan_course(ps):
    """찜한 곳을 이동 거리가 가장 짧은 순서로 (곳이 적으면 모든 순서를 비교, 많으면 가까운 곳부터 차례로)"""
    if len(ps) <= 7:
        return list(min(permutations(ps), key=lambda o: sum(km(a, b) for a, b in zip(o, o[1:]))))
    course, rest = [ps[0]], ps[1:]
    while rest:
        nxt = min(rest, key=lambda p: km(course[-1], p))
        rest.remove(nxt)
        course.append(nxt)
    return course


MAP_HTML = """
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  html, body {{ margin: 0; }}
  #map {{ height: {height}px; border-radius: 16px; }}
  .leaflet-tile-pane {{ filter: saturate(.55) brightness(1.04); }}
  .pin {{ width: 28px; height: 28px; border-radius: 50%; color: #fff; font: 700 13px sans-serif;
          display: flex; align-items: center; justify-content: center; border: 2px solid #fff;
          box-shadow: 0 2px 6px rgba(0,0,0,.35); }}
</style>
<div id="map"></div>
<script>
  const pts = {points};
  const map = L.map("map", {{ scrollWheelZoom: false }});
  L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
    maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }}).addTo(map);
  pts.forEach(p => L.marker([p.lat, p.lon], {{ icon: L.divIcon({{ className: "",
      html: `<div class="pin" style="background:${{p.color}}">${{p.label}}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] }}) }})
    .addTo(map).bindPopup(`<b>${{p.label}}. ${{p.name}}</b><br>${{p.info}}`));
  if ({path} && pts.length > 1) L.polyline(pts.map(p => [p.lat, p.lon]), {{ color: "#0071E3", weight: 4, opacity: .7 }}).addTo(map);
  if (pts.length > 1) map.fitBounds(pts.map(p => [p.lat, p.lon]), {{ padding: [40, 40] }});
  else map.setView([pts[0].lat, pts[0].lon], 15);
</script>
"""


def show_map(ps, path=False, height=420):
    """장소들을 번호 핀으로 지도(Leaflet + 무료 OpenStreetMap 지도, 키 필요 없음)에 표시. path=True면 순서대로 선을 잇는다."""
    ps = [p for p in ps if p.get("lat")]
    if not ps:
        st.info("지도에 표시할 좌표가 없어요.")
        return
    points = [{"lat": p["lat"], "lon": p["lon"], "label": i, "name": escape(p["name"]),
               "info": f"{TYPE_ICON.get(p['type'], '')} {p['type']} · {p['region']}", "color": TYPE_COLOR.get(p["type"], "#888")}
              for i, p in enumerate(ps, 1)]
    data = json.dumps(points, ensure_ascii=False).replace("</", "<\\/")  # 글 속 </script>가 코드를 끊지 않게
    st.iframe(MAP_HTML.format(points=data, path="true" if path else "false", height=height), height=height + 10)
    st.caption("핀 색: 🛍️ 팝업 빨강 · 🖼️ 전시 보라 · ☕ 카페 주황 · 핀을 누르면 이름이 나와요. "
               "뉴스로 찾은 팝업은 동네 대표 위치예요.")


def show_card(rank, p, score, best, day):
    with st.container(border=True):
        if p.get("image"):
            st.markdown(f'<img class="thumb" src="{escape(p["image"])}" alt="">', unsafe_allow_html=True)
        else:  # 사진이 없는 곳(뉴스로 찾은 팝업)은 종류 아이콘으로
            st.markdown(f'<div class="noimg">{TYPE_ICON.get(p["type"], "🎈")}</div>', unsafe_allow_html=True)

        price = "가격 미확인" if p["price"] is None else ("무료" if p["price"] == 0 else f"{p['price']:,}원")
        chips = [f"{TYPE_ICON.get(p['type'], '')} {p['type']}", f"📍 {p['region']}", f"💳 {price}", f"📅 {period_text(p)}"]
        b = badge(p, day)
        desc = p["desc"] if len(p["desc"]) <= DESC_LEN else p["desc"][:DESC_LEN] + "…"
        link = f' <a href="{escape(p["source"])}" target="_blank">공식 안내 →</a>' if p.get("source") else ""
        st.markdown(
            f'<div class="title"><span class="rank">{rank}</span>{escape(p["name"])}</div>'
            + (f'<span class="chip {b[1]}">{b[0]}</span>' if b else "")
            + "".join(f'<span class="chip">{escape(c)}</span>' for c in chips)
            + f'<div class="reason">💡 {escape(reason_text(best))} <small>(점수 {score:.2f})</small></div>'
            + f'<div class="desc">{escape(desc)}{link}</div>',
            unsafe_allow_html=True)

        fb = st.session_state.feedback
        liked = p["id"] in fb["liked"]
        c1, c2 = st.columns(2)
        if c1.button("❤️ 찜 취소" if liked else "🤍 찜하기", key=f"like{p['id']}", use_container_width=True):
            (fb["liked"].discard if liked else fb["liked"].add)(p["id"])
            st.rerun()
        if c2.button("👎 별로예요", key=f"dislike{p['id']}", use_container_width=True):
            fb["disliked"].add(p["id"])
            fb["liked"].discard(p["id"])
            st.rerun()


def show_course(places, day):
    fb = st.session_state.feedback
    by_id = {p["id"]: p for p in places}
    liked = [by_id[i] for i in fb["liked"] if i in by_id]
    if not liked:
        st.markdown('<div class="empty"><div>🤍</div>추천 카드에서 <b>찜하기</b>를 누르면 여기에 모여요.<br>'
                    '2곳 이상 찜하면 가까운 순서로 하루 코스를 짜 드려요.</div>', unsafe_allow_html=True)
        return
    course = plan_course(liked) if len(liked) > 1 else liked
    total = sum(km(a, b) for a, b in zip(course, course[1:]))
    st.markdown(f'<div class="section">🧭 오늘의 코스 · {len(course)}곳'
                + (f' · 총 이동 약 {total:.1f}km' if len(course) > 1 else "") + '</div>', unsafe_allow_html=True)
    for i, p in enumerate(course, 1):
        ok, why = rec.is_open(p, day.isoformat())
        note = "" if ok else f" <span class='chip soon'>방문일엔 {why}</span>"
        c1, c2 = st.columns([5, 1])
        c1.markdown(f'<div class="step"><span class="num">{i}</span><div><b>{TYPE_ICON.get(p["type"], "")} '
                    f'{escape(p["name"])}</b>{note}<br><small>{p["region"]} · {period_text(p)}</small></div></div>',
                    unsafe_allow_html=True)
        if c2.button("빼기", key=f"unlike{p['id']}", use_container_width=True):
            fb["liked"].discard(p["id"])
            st.rerun()
        if i < len(course):
            d = km(p, course[i])
            st.markdown(f'<div class="move">↓ {"🚶 걸어서" if d < 1.5 else "🚇 대중교통으로"} · 직선 {d:.1f}km</div>',
                        unsafe_allow_html=True)
    show_map(course, path=True)
    if fb["disliked"]:
        st.caption("👎 별로예요 표시: " + ", ".join(by_id[i]["name"] for i in fb["disliked"] if i in by_id))
    if st.button("찜·별로예요 모두 지우기"):
        st.session_state.feedback = {"liked": set(), "disliked": set()}
        st.rerun()


def show_mini(p, day):
    """전체 둘러보기용 작은 카드"""
    with st.container(border=True):
        if p.get("image"):
            st.markdown(f'<img class="thumb mini" src="{escape(p["image"])}" alt="">', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="noimg mini">{TYPE_ICON.get(p["type"], "🎈")}</div>', unsafe_allow_html=True)
        price = "가격 미확인" if p["price"] is None else ("무료" if p["price"] == 0 else f"{p['price']:,}원")
        b = badge(p, day)
        link = f'<a href="{escape(p["source"])}" target="_blank">공식 안내 →</a>' if p.get("source") else ""
        st.markdown(
            f'<div class="mtitle">{escape(p["name"])}</div>'
            + (f'<span class="chip {b[1]}">{b[0]}</span>' if b else "")
            + f'<span class="chip">{TYPE_ICON.get(p["type"], "")} {p["type"]}</span>'
            + f'<span class="chip">📍 {p["region"]}</span><span class="chip">💳 {price}</span>'
            + f'<div class="desc">📅 {period_text(p)} · {link}</div>',
            unsafe_allow_html=True)
        liked = p["id"] in st.session_state.feedback["liked"]
        if st.button("❤️ 찜 취소" if liked else "🤍 찜하기", key=f"like{p['id']}", use_container_width=True):
            (st.session_state.feedback["liked"].discard if liked else st.session_state.feedback["liked"].add)(p["id"])
            st.rerun()


def show_browse(places, day, ans):
    """고른 지역의 팝업·전시·카페 전체 목록 (방문일에 열려 있는 곳만)"""
    kinds = st.pills("종류", TYPES, selection_mode="multi", default=TYPES, key="browse_types",
                     format_func=lambda t: f"{TYPE_ICON[t]} {t}")
    c2, c3 = st.columns([2.4, 1])  # 종류 버튼은 한 줄을 다 쓰고, 지역·정렬은 그 아래 줄에
    picked = (ans or {}).get("regions") or []  # 질문지에서 고른 지역을 기본으로 (질문지가 바뀌면 새로 맞춤)
    regions = c2.multiselect("지역 (비워 두면 서울 전체)", sorted({p["region"] for p in places}),
                             default=picked, key=f"browse_regions_{'_'.join(picked)}")
    order = c3.selectbox("정렬", ["마감 임박순", "새로 오픈순", "이름순"], key="browse_order")

    items = [p for p in places if p["type"] in (kinds or TYPES) and (not regions or p["region"] in regions)
             and rec.is_open(p, day.isoformat())[0]]
    if order == "마감 임박순":
        items.sort(key=lambda p: p["end"] or "9999")  # 상설(카페)은 뒤로
    elif order == "새로 오픈순":
        items.sort(key=lambda p: p["start"] or "0000", reverse=True)
    else:
        items.sort(key=lambda p: p["name"])

    count = {t: sum(p["type"] == t for p in items) for t in TYPES}
    st.markdown(f'<div class="section">📋 {", ".join(regions) if regions else "서울 전체"} · {day:%m월 %d일}에 갈 수 있는 곳 '
                f'{len(items)}곳 <small>(' + " · ".join(f"{TYPE_ICON[t]} {count[t]}" for t in TYPES) + ')</small></div>',
                unsafe_allow_html=True)
    if not items:
        st.info("조건에 맞는 곳이 없어요. 종류나 지역을 바꿔 보세요.")
        return
    shown = st.session_state.setdefault("browse_n", BROWSE_PAGE)
    cols = st.columns(3, gap="small")
    for i, p in enumerate(items[:shown]):
        with cols[i % 3]:
            show_mini(p, day)
    if shown < len(items) and st.button(f"더 보기 ({shown}/{len(items)})", use_container_width=True):
        st.session_state.browse_n += BROWSE_PAGE
        st.rerun()


# ---------------- 스와이프로 취향 고르기 (Tinder 방식) ----------------
SWIPE_CSS = """
:host { font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", Pretendard, sans-serif; }
.wrap { display: flex; flex-direction: column; align-items: center; user-select: none; }
.deck { position: relative; width: 100%; max-width: 360px; height: 500px; }
.card { position: absolute; inset: 0; background: #fff; border-radius: 26px; overflow: hidden;
        box-shadow: 0 12px 36px rgba(0,0,0,.12); touch-action: none; cursor: grab;
        transition: transform .3s cubic-bezier(.2,.8,.2,1), opacity .3s; }
.card.dragging { transition: none; cursor: grabbing; }
.card.back1 { transform: translateY(14px) scale(.95); opacity: .9; }
.card.back2 { transform: translateY(28px) scale(.90); opacity: .6; }
.img { height: 270px; background: linear-gradient(135deg, #F5F5F7, #E8E8ED) center/cover no-repeat;
       display: flex; align-items: center; justify-content: center; font-size: 80px; pointer-events: none; }
.body { padding: 16px 20px; }
.name { font-size: 1.3rem; font-weight: 700; letter-spacing: -0.02em; color: #1D1D1F; line-height: 1.3;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.chips { margin: 8px 0 6px; }
.chip { display: inline-block; padding: 3px 10px; margin: 0 4px 4px 0; border-radius: 999px;
        background: #F5F5F7; color: #424245; font-size: .76rem; font-weight: 500; }
.chip.soon { background: #FFE5E3; color: #D70015; font-weight: 600; }
.chip.new { background: #E3F0FF; color: #0071E3; font-weight: 600; }
.reason { background: #F5F5F7; border-radius: 12px; padding: 8px 12px; font-size: .86rem; color: #1D1D1F; }
.desc { color: #6E6E73; font-size: .82rem; line-height: 1.5; margin-top: 8px;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.stamp { position: absolute; top: 26px; padding: 6px 14px; border: 4px solid; border-radius: 12px;
         font-size: 1.6rem; font-weight: 800; opacity: 0; background: rgba(255,255,255,.85); }
.stamp.like { left: 22px; color: #34C759; transform: rotate(-14deg); }
.stamp.nope { right: 22px; color: #FF3B30; transform: rotate(14deg); }
.btns { display: flex; gap: 28px; margin-top: 22px; }
.btn { width: 64px; height: 64px; border-radius: 50%; border: none; background: #fff; font-size: 28px; cursor: pointer;
       box-shadow: 0 4px 16px rgba(0,0,0,.12); transition: transform .15s; }
.btn:hover { transform: scale(1.08); }
.btn:active { transform: scale(.95); }
.btn.nope { color: #FF3B30; }
.btn.like { color: #34C759; }
.hint { color: #6E6E73; font-size: .8rem; margin-top: 12px; }
.done { height: 500px; display: flex; flex-direction: column; align-items: center; justify-content: center;
        color: #6E6E73; text-align: center; line-height: 1.7; }
.done div { font-size: 56px; }
"""

SWIPE_JS = """
export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  parentElement.querySelector('.wrap')?.remove();  // 새 카드 묶음이 오면 처음부터 다시 그린다
  const wrap = document.createElement('div');
  wrap.className = 'wrap';
  parentElement.appendChild(wrap);
  const cards = (data && data.cards) || [];
  if (!cards.length) {
    wrap.innerHTML = '<div class="done"><div>🎉</div><b>조건에 맞는 곳을 모두 봤어요</b>' +
                     '찜한 곳은 ‘찜·코스’에서 하루 코스로 만들 수 있어요.</div>';
    return;
  }
  // 장소 글은 textContent로만 넣는다 (HTML로 해석되지 않게)
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls;
                                   if (text != null) e.textContent = text; return e; };
  const deck = el('div', 'deck');
  wrap.appendChild(deck);
  const shown = cards.slice(0, 3);
  for (let pos = shown.length - 1; pos >= 0; pos--) {   // 뒤 카드부터 쌓고 맨 앞(pos 0)을 마지막에
    const c = shown[pos];
    const card = el('div', 'card' + (pos ? ' back' + pos : ''));
    const img = el('div', 'img');
    if (c.image) img.style.backgroundImage = 'url("' + encodeURI(c.image) + '")'; else img.textContent = c.icon;
    const body = el('div', 'body');
    body.appendChild(el('div', 'name', c.name));
    const chips = el('div', 'chips');
    if (c.badge) chips.appendChild(el('span', 'chip ' + c.badge[1], c.badge[0]));
    c.chips.forEach(t => chips.appendChild(el('span', 'chip', t)));
    body.append(chips, el('div', 'reason', '💡 ' + c.reason), el('div', 'desc', c.desc));
    card.append(img, body, el('div', 'stamp like', '찜!'), el('div', 'stamp nope', '별로'));
    card.dataset.id = c.id;
    deck.appendChild(card);
  }
  const top = deck.lastChild;
  const like = top.querySelector('.stamp.like'), nope = top.querySelector('.stamp.nope');
  let sent = false;

  function fly(dir) {
    if (sent) return;
    sent = true;
    const s = dir === 'right' ? 1 : -1;
    top.style.transform = 'translateX(' + 600 * s + 'px) rotate(' + 30 * s + 'deg)';
    top.style.opacity = '0';
    (dir === 'right' ? like : nope).style.opacity = 1;
    deck.querySelectorAll('.card.back1').forEach(c => c.classList.remove('back1'));  // 뒤 카드가 앞으로
    setTimeout(() => setTriggerValue('swipe', { id: top.dataset.id, dir: dir, t: Date.now() }), 280);
  }

  let x0 = null, dx = 0;
  top.addEventListener('pointerdown', e => {
    x0 = e.clientX; dx = 0; top.classList.add('dragging'); top.setPointerCapture(e.pointerId);
  });
  top.addEventListener('pointermove', e => {
    if (x0 === null) return;
    dx = e.clientX - x0;
    top.style.transform = 'translateX(' + dx + 'px) rotate(' + dx / 18 + 'deg)';
    like.style.opacity = Math.max(0, Math.min(1, dx / 100));
    nope.style.opacity = Math.max(0, Math.min(1, -dx / 100));
  });
  const end = () => {
    if (x0 === null) return;
    x0 = null;
    top.classList.remove('dragging');
    if (Math.abs(dx) > 110) fly(dx > 0 ? 'right' : 'left');
    else { top.style.transform = ''; like.style.opacity = 0; nope.style.opacity = 0; }
  };
  top.addEventListener('pointerup', end);
  top.addEventListener('pointercancel', end);

  const btns = el('div', 'btns');
  const bNope = el('button', 'btn nope', '✕'), bLike = el('button', 'btn like', '♥');
  bNope.title = '별로예요 (←)';
  bLike.title = '찜하기 (→)';
  bNope.onclick = () => fly('left');
  bLike.onclick = () => fly('right');
  btns.append(bNope, bLike);
  wrap.append(btns, el('div', 'hint', '카드를 좌우로 밀거나, 버튼 또는 키보드 ← → 를 눌러요'));

  const onKey = e => {
    const tag = document.activeElement && document.activeElement.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (e.key === 'ArrowRight') fly('right');
    if (e.key === 'ArrowLeft') fly('left');
  };
  document.addEventListener('keydown', onKey);
  return () => document.removeEventListener('keydown', onKey);
}
"""

swipe_deck = st.components.v2.component("moodmatch_swipe", css=SWIPE_CSS, js=SWIPE_JS)
SWIPE_STACK = 3  # 한 번에 겹쳐 보여 줄 카드 수


def on_swipe():
    """카드를 넘기면 (화면을 다시 그리기 전에) 찜 / 별로예요에 반영한다."""
    ev = (st.session_state.get("swipe_deck") or {}).get("swipe")
    if not ev or ev.get("t") == st.session_state.get("swipe_last_t"):
        return
    st.session_state.swipe_last_t = ev.get("t")
    fb = st.session_state.feedback
    if ev["dir"] == "right":
        fb["liked"].add(ev["id"])
    else:
        fb["disliked"].add(ev["id"])
        fb["liked"].discard(ev["id"])
    st.session_state.setdefault("swipe_log", []).append((ev["id"], ev["dir"]))


def swipe_card_data(p, best, day):
    price = "가격 미확인" if p["price"] is None else ("무료" if p["price"] == 0 else f"{p['price']:,}원")
    desc = p["desc"] if len(p["desc"]) <= DESC_LEN else p["desc"][:DESC_LEN] + "…"
    return {"id": p["id"], "name": p["name"], "image": p.get("image") or "", "icon": TYPE_ICON.get(p["type"], "🎈"),
            "chips": [f"{TYPE_ICON.get(p['type'], '')} {p['type']}", f"📍 {p['region']}", f"💳 {price}",
                      f"📅 {period_text(p)}"],
            "badge": badge(p, day), "reason": reason_text(best), "desc": desc}


def taste_bars(items, color):
    top = max(abs(v) for _, v in items) or 1
    return "".join(f'<div class="tbar"><span>{escape(o)}</span><i style="width:{max(6, abs(v) / top * 100):.0f}%;'
                   f'background:{color}"></i></div>' for o, v in items)


def show_swipe(model, places, place_vecs, ans, day):
    fb = st.session_state.feedback
    log = st.session_state.setdefault("swipe_log", [])
    deck, _ = rec.recommend(model, places, ans, top_n=SWIPE_STACK, place_vecs=place_vecs, liked=fb["liked"],
                            disliked=fb["disliked"], exclude=fb["liked"] | fb["disliked"], diverse=False)
    c1, c2 = st.columns([1.2, 1], gap="large")
    with c1:
        swipe_deck(data={"cards": [swipe_card_data(p, best, day) for p, _, best in deck]},
                   key="swipe_deck", on_swipe_change=on_swipe)
    with c2:
        n_like = sum(d == "right" for _, d in log)
        st.markdown(f'<div class="section">취향 학습 중</div>'
                    f'<div class="swstat"><div><b style="color:#34C759">♥ {n_like}</b><small>찜</small></div>'
                    f'<div><b style="color:#FF3B30">✕ {len(log) - n_like}</b><small>별로</small></div></div>',
                    unsafe_allow_html=True)
        prof = rec.taste_profile(model, places, place_vecs, fb["liked"], fb["disliked"], ACTIVITIES + MOODS)
        if not prof:
            st.markdown('<div class="desc">마음에 드는 카드를 <b>오른쪽</b>으로 넘겨 보세요. '
                        '넘길수록 다음 카드가 내 취향에 맞게 바뀌어요.</div>', unsafe_allow_html=True)
        else:
            like_side = [x for x in prof[:3] if x[1] > 0]
            dis_side = [x for x in prof[-2:] if x[1] < 0] if fb["disliked"] else []
            html = ""
            if like_side:
                html += '<div class="tlabel">반응으로 알아낸 취향</div>' + taste_bars(like_side, "#0071E3")
            if dis_side:
                html += '<div class="tlabel">덜 끌리는 것</div>' + taste_bars(dis_side[::-1], "#C7C7CC")
            st.markdown(html, unsafe_allow_html=True)
            st.caption("찜한 곳과 비슷한 곳은 점수를 올리고, 별로예요와 비슷한 곳은 내려서 다음 카드를 골라요. "
                       "‘🎯 추천 결과’도 다음 추천받기 때 이 반응을 반영해요.")
        if log and st.button("↩︎ 방금 넘긴 카드 되돌리기", use_container_width=True):
            pid, d = log.pop()
            (fb["liked"] if d == "right" else fb["disliked"]).discard(pid)
            st.rerun()


st.set_page_config(page_title="MoodMatch", page_icon="🎈", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown('<div class="hero"><div class="eyebrow">MoodMatch</div>'
            '<h1>오늘 기분에 꼭 맞는 곳,<br><span>지금 바로.</span></h1>'
            '<p>취향 질문 몇 개에 답하면, 지금 갈 수 있는 서울의 팝업·전시·카페를 골라 드려요.</p></div>',
            unsafe_allow_html=True)

model, places, place_vecs = load_data(tuple(f.stat().st_mtime if f.exists() else 0
                                            for f in (rec.PLACES_FILE, rec.VECS_FILE)))
if "feedback" not in st.session_state:
    st.session_state.feedback = {"liked": set(), "disliked": set()}
if "answers" not in st.session_state:
    st.session_state.answers = None

left, right = st.columns([1, 1.75], gap="large")

with left, st.form("survey"):
    st.markdown('<div class="section">📝 취향 질문지</div>', unsafe_allow_html=True)
    types = st.multiselect("Q1. 어디에 가고 싶어요?", TYPES, default=TYPES)
    activity = st.multiselect("Q2. 가서 뭘 하고 싶어요? (고른 순서 = 1~3순위)", ACTIVITIES, max_selections=3)
    mood = st.multiselect("Q3. 원하는 분위기는? (고른 순서 = 1~3순위)", MOODS, max_selections=3)
    with_ = st.radio("Q4. 누구랑 가요?", COMPANIONS, horizontal=True)
    day = st.date_input("Q5. 방문 날짜", value=date.today(), min_value=date.today())
    budget = st.select_slider("1인 예산", options=list(BUDGETS), value="1만 원")
    regions = st.multiselect("지역 (비워 두면 서울 전체)", sorted({p["region"] for p in places}))
    submitted = st.form_submit_button("✨ 추천받기", type="primary", use_container_width=True)

if submitted:
    if not types or not activity or not mood:
        left.warning("Q1~Q3는 하나 이상 골라 주세요.")
        st.session_state.answers = None
    else:
        st.session_state.answers = {
            "types": types, "activity_rank": activity, "mood_rank": mood, "with": with_,
            "date": day.isoformat(), "regions": regions or None, "budget": BUDGETS[budget],
        }
        # 찜은 다음 추천받기 때 반영한다 (찜을 누를 때마다 카드가 바뀌어 사라지지 않게)
        st.session_state.liked_at_submit = set(st.session_state.feedback["liked"])

with right:
    ans = st.session_state.answers
    fb = st.session_state.feedback
    visit = date.fromisoformat(ans["date"]) if ans else date.today()
    top = []
    if ans:
        top, _ = rec.recommend(model, places, ans, top_n=TOP_N, place_vecs=place_vecs,
                               liked=st.session_state.get("liked_at_submit", set()), disliked=fb["disliked"])
        taste_card(ans)
    # 탭은 숨은 탭의 지도가 빈 화면으로 그려질 때가 있어서, 고른 화면 하나만 그리는 선택 버튼을 쓴다
    views = {"rec": "🎯 추천 결과", "swipe": "💫 스와이프", "map": "🗺️ 지도로 보기", "browse": "📋 전체 둘러보기",
             "course": f"❤️ 찜·코스 ({len(fb['liked'])})"}
    view = st.radio("보기", list(views), format_func=views.get, horizontal=True,
                    label_visibility="collapsed", key="view")
    if view in ("rec", "swipe", "map") and not ans:
        st.markdown(f'<div class="empty"><div>🔍</div>왼쪽 질문지에 답하고 <b>추천받기</b>를 눌러 보세요.<br>'
                    f'지금 열려 있는 {len(places)}곳 중에서 골라 드려요. '
                    f'먼저 구경하고 싶으면 <b>📋 전체 둘러보기</b>를 눌러 보세요.</div>', unsafe_allow_html=True)
    elif view == "rec":
        st.caption("🤍 찜한 곳은 ‘찜·코스’에 모이고, 다음에 추천받기를 누르면 비슷한 곳을 더 찾아 줘요. "
                   "👎 별로예요는 바로 빼고 다른 곳으로 채워요.")
        if not top:
            st.info("조건에 맞는 곳이 없어요. 날짜, 지역, 예산을 바꿔 보세요.")
        cols = st.columns(2, gap="medium")
        for i, (p, score, best) in enumerate(top, 1):
            with cols[(i - 1) % 2]:
                show_card(i, p, score, best, visit)
    elif view == "swipe":
        show_swipe(model, places, place_vecs, ans, visit)
    elif view == "map":
        show_map([p for p, _, _ in top])
    elif view == "browse":
        show_browse(places, visit, ans)
    else:
        show_course(places, visit)
