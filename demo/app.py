"""MoodMatch 웹: 취향 질문지 5문항에 답하면 지금 갈 수 있는 팝업·전시·카페 Top 6를 추천한다.
추천 결과 · 지도 · 찜한 곳으로 짜는 하루 코스를 탭으로 보여 준다.

실행: streamlit run demo/app.py
"""
from datetime import date
from html import escape
from itertools import permutations
from math import asin, cos, radians, sin, sqrt

import pandas as pd
import pydeck as pdk
import streamlit as st

import recommend as rec

TYPES = ["팝업", "전시", "카페"]
ACTIVITIES = ["체험", "사진", "굿즈", "관람", "음식"]
MOODS = ["귀여운", "조용한", "트렌디", "예술적", "레트로"]
COMPANIONS = ["혼자", "친구", "연인", "가족"]
BUDGETS = {"무료만": 0, "5천 원": 5000, "1만 원": 10000, "2만 원": 20000, "3만 원": 30000, "상관없음": 10**9}
TYPE_ICON = {"팝업": "🛍️", "전시": "🖼️", "카페": "☕"}
TYPE_COLOR = {"팝업": [255, 107, 91], "전시": [124, 92, 255], "카페": [214, 140, 60]}  # 지도 핀 색
DESC_LEN = 110  # 카드에 보일 소개글 길이
TOP_N = 6       # 추천 개수 (2열로 3줄)
SOON_DAYS = 7   # 끝나기 7일 전부터 '곧 끝나요', 연 지 7일 안이면 'NEW'

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
html, body, [class*="st-"], button, input, textarea { font-family: Pretendard, sans-serif; }
.block-container { padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1180px; }
header[data-testid="stHeader"] { background: transparent; }
.hero { background: linear-gradient(120deg, #FF7A6B 0%, #FF9E7D 55%, #FFC48C 100%);
        color: #fff; border-radius: 22px; padding: 22px 28px; margin-bottom: 18px; }
.hero h1 { color: #fff; font-size: 2rem; font-weight: 800; margin: 0; padding: 0; }
.hero p { margin: 4px 0 0; opacity: .95; font-size: 1rem; }
.section { font-weight: 700; font-size: 1.1rem; margin: 2px 0 8px; }
div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #fff; border-radius: 18px; border: 1px solid #F6DDD3;
        box-shadow: 0 4px 14px rgba(255, 107, 91, .08); }
.taste { background: linear-gradient(120deg, #FFF0EA, #FFF7E6); border: 1px solid #FFD9CC; border-radius: 18px;
         padding: 14px 20px; margin-bottom: 12px; display: flex; align-items: center; gap: 16px; }
.taste .emoji { font-size: 44px; }
.taste small { color: #9A6B5E; }
.taste b { font-size: 1.25rem; color: #D2473A; }
.thumb { width: 100%; height: 190px; object-fit: cover; border-radius: 14px; display: block; }
.noimg { height: 190px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
         font-size: 64px; background: linear-gradient(135deg, #FFE1D6, #FFF1D9); }
.title { font-size: 1.15rem; font-weight: 800; line-height: 1.35; margin: 8px 0 6px; }
.rank { display: inline-block; background: #FF6B5B; color: #fff; border-radius: 999px;
        width: 26px; height: 26px; line-height: 26px; text-align: center; font-size: .85rem; margin-right: 6px; }
.chip { display: inline-block; padding: 2px 10px; margin: 0 4px 4px 0; border-radius: 999px;
        background: #FFEDE6; color: #C8463A; font-size: .78rem; font-weight: 600; }
.chip.soon { background: #FF4D4F; color: #fff; }
.chip.new { background: #22B07D; color: #fff; }
.reason { background: #FFF6F0; border-left: 4px solid #FF6B5B; border-radius: 8px;
          padding: 7px 11px; margin: 6px 0; font-size: .9rem; }
.desc { color: #5B5761; font-size: .88rem; line-height: 1.5; margin: 4px 0; }
.desc a { color: #FF6B5B; font-weight: 600; text-decoration: none; }
.step { display: flex; gap: 12px; align-items: center; }
.step .num { background: #FF6B5B; color: #fff; border-radius: 999px; min-width: 30px; height: 30px;
             line-height: 30px; text-align: center; font-weight: 700; }
.move { color: #9A8F8A; font-size: .85rem; margin: 2px 0 2px 42px; }
.empty { text-align: center; color: #9A8F8A; padding: 60px 20px; }
.empty div { font-size: 52px; }
</style>
"""


@st.cache_resource(show_spinner="AI 모델을 불러오는 중… (처음 한 번만)")
def load():
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
    """두 장소 사이 직선거리(km)"""
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


def show_map(ps, path=False):
    """장소들을 번호 핀으로 지도에 표시. path=True면 순서대로 선을 잇는다."""
    ps = [p for p in ps if p.get("lat")]
    if not ps:
        st.info("지도에 표시할 좌표가 없어요.")
        return
    df = pd.DataFrame([{"lat": p["lat"], "lon": p["lon"], "name": p["name"], "label": str(i),
                        "info": f"{p['type']} · {p['region']}", "color": TYPE_COLOR.get(p["type"], [120, 120, 120])}
                       for i, p in enumerate(ps, 1)])
    layers = [
        pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_fill_color="color",
                  get_radius=14, radius_units="pixels", pickable=True, stroked=True,
                  get_line_color=[255, 255, 255], line_width_min_pixels=2),
        pdk.Layer("TextLayer", df, get_position="[lon, lat]", get_text="label", get_size=14,
                  get_color=[255, 255, 255], get_text_anchor="'middle'", get_alignment_baseline="'center'"),
    ]
    if path and len(ps) > 1:
        layers.insert(0, pdk.Layer("PathLayer", [{"path": [[p["lon"], p["lat"]] for p in ps]}], get_path="path",
                                   get_color=[255, 107, 91, 160], width_min_pixels=4))
    view = pdk.ViewState(latitude=df["lat"].mean(), longitude=df["lon"].mean(),
                         zoom=11 if len(ps) > 1 else 13)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_style="light",
                             tooltip={"text": "{label}. {name}\n{info}"}), height=420)
    st.caption("  ".join(f"{TYPE_ICON[t]} {t}" for t in TYPES) + " — 핀 색: 팝업 빨강 · 전시 보라 · 카페 주황. "
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
        if c1.button("❤️ 찜함" if liked else "🤍 찜하기", key=f"like{p['id']}", disabled=liked, use_container_width=True):
            fb["liked"].add(p["id"])
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


st.set_page_config(page_title="MoodMatch", page_icon="🎈", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>🎈 MoodMatch</h1>'
            '<p>취향 질문 몇 개에 답하면, 지금 갈 수 있는 서울의 팝업·전시·카페를 골라 드려요.</p></div>',
            unsafe_allow_html=True)

model, places, place_vecs = load()
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

with right:
    ans = st.session_state.answers
    if not ans:
        st.markdown(f'<div class="empty"><div>🔍</div>왼쪽 질문지에 답하고 <b>추천받기</b>를 눌러 보세요.<br>'
                    f'지금 열려 있는 {len(places)}곳 중에서 골라 드려요.</div>', unsafe_allow_html=True)
    else:
        fb = st.session_state.feedback
        visit = date.fromisoformat(ans["date"])
        top, _ = rec.recommend(model, places, ans, top_n=TOP_N, place_vecs=place_vecs,
                               liked=fb["liked"], disliked=fb["disliked"])
        taste_card(ans)
        tab_rec, tab_map, tab_course = st.tabs(["🎯 추천 결과", "🗺️ 지도로 보기", f"❤️ 찜·코스 ({len(fb['liked'])})"])
        with tab_rec:
            if not top:
                st.info("조건에 맞는 곳이 없어요. 날짜, 지역, 예산을 바꿔 보세요.")
            cols = st.columns(2, gap="medium")
            for i, (p, score, best) in enumerate(top, 1):
                with cols[(i - 1) % 2]:
                    show_card(i, p, score, best, visit)
        with tab_map:
            show_map([p for p, _, _ in top])
        with tab_course:
            show_course(places, visit)
