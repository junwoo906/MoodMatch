"""MoodMatch 웹: 취향 질문지 5문항에 답하면 지금 갈 수 있는 팝업·전시·카페 Top 3를 추천한다.

실행: streamlit run demo/app.py
"""
from datetime import date
from html import escape

import streamlit as st

import recommend as rec

TYPES = ["팝업", "전시", "카페"]
ACTIVITIES = ["체험", "사진", "굿즈", "관람", "음식"]
MOODS = ["귀여운", "조용한", "트렌디", "예술적", "레트로"]
COMPANIONS = ["혼자", "친구", "연인", "가족"]
BUDGETS = {"무료만": 0, "5천 원": 5000, "1만 원": 10000, "2만 원": 20000, "3만 원": 30000, "상관없음": 10**9}
TYPE_ICON = {"팝업": "🛍️", "전시": "🖼️", "카페": "☕"}
DESC_LEN = 140  # 카드에 보일 소개글 길이

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
.thumb { width: 100%; height: 200px; object-fit: cover; border-radius: 14px; display: block; }
.noimg { height: 200px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
         font-size: 64px; background: linear-gradient(135deg, #FFE1D6, #FFF1D9); }
.title { font-size: 1.2rem; font-weight: 800; line-height: 1.35; margin: 0 0 6px; }
.rank { display: inline-block; background: #FF6B5B; color: #fff; border-radius: 999px;
        width: 26px; height: 26px; line-height: 26px; text-align: center; font-size: .85rem; margin-right: 6px; }
.chip { display: inline-block; padding: 2px 10px; margin: 0 4px 4px 0; border-radius: 999px;
        background: #FFEDE6; color: #C8463A; font-size: .78rem; font-weight: 600; }
.reason { background: #FFF6F0; border-left: 4px solid #FF6B5B; border-radius: 8px;
          padding: 7px 11px; margin: 6px 0; font-size: .9rem; }
.desc { color: #5B5761; font-size: .88rem; line-height: 1.5; margin: 4px 0; }
.desc a { color: #FF6B5B; font-weight: 600; text-decoration: none; }
.empty { text-align: center; color: #9A8F8A; padding: 70px 20px; }
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
        return f"좋아요한 ‘{best[5:]}’와 비슷해요"
    if best in ACTIVITIES:
        return f"‘{best}’ 하고 싶은 마음과 가장 잘 맞아요"
    if best in MOODS:
        return f"‘{best}’ 분위기와 가장 잘 맞아요"
    return f"{best} 가기 좋은 곳이에요"


def period_text(p):
    if not p["start"] and not p["end"]:
        return "상설"
    return f"{p['start'] or ''} ~ {p['end'] or ''}"


def show_card(rank, p, score, best):
    with st.container(border=True):
        img, body = st.columns([1, 1.7], gap="medium")
        if p.get("image"):
            img.markdown(f'<img class="thumb" src="{escape(p["image"])}" alt="">', unsafe_allow_html=True)
        else:  # 사진이 없는 곳(뉴스로 찾은 팝업)은 종류 아이콘으로
            img.markdown(f'<div class="noimg">{TYPE_ICON.get(p["type"], "🎈")}</div>', unsafe_allow_html=True)

        price = "가격 미확인" if p["price"] is None else ("무료" if p["price"] == 0 else f"{p['price']:,}원")
        chips = [f"{TYPE_ICON.get(p['type'], '')} {p['type']}", f"📍 {p['region']}", f"💳 {price}", f"📅 {period_text(p)}"]
        desc = p["desc"] if len(p["desc"]) <= DESC_LEN else p["desc"][:DESC_LEN] + "…"
        link = f' <a href="{escape(p["source"])}" target="_blank">공식 안내 →</a>' if p.get("source") else ""
        body.markdown(
            f'<div class="title"><span class="rank">{rank}</span>{escape(p["name"])}</div>'
            + "".join(f'<span class="chip">{escape(c)}</span>' for c in chips)
            + f'<div class="reason">💡 {escape(reason_text(best))} <small>(점수 {score:.2f})</small></div>'
            + f'<div class="desc">{escape(desc)}{link}</div>',
            unsafe_allow_html=True)

        fb = st.session_state.feedback
        c1, c2, _ = body.columns([1, 1, 1.2])
        if c1.button("👍 좋아요", key=f"like{p['id']}", disabled=p["id"] in fb["liked"], use_container_width=True):
            fb["liked"].add(p["id"])
            st.rerun()
        if c2.button("👎 별로예요", key=f"dislike{p['id']}", use_container_width=True):
            fb["disliked"].add(p["id"])
            fb["liked"].discard(p["id"])
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
        top, excluded = rec.recommend(model, places, ans, place_vecs=place_vecs,
                                      liked=fb["liked"], disliked=fb["disliked"])
        st.markdown('<div class="section">🎯 오늘의 추천</div>', unsafe_allow_html=True)
        if not top:
            st.info("조건에 맞는 곳이 없어요. 날짜, 지역, 예산을 바꿔 보세요.")
        for i, (p, score, best) in enumerate(top, 1):
            show_card(i, p, score, best)

        if fb["liked"] or fb["disliked"]:
            names = {p["id"]: p["name"] for p in places}
            st.caption("반영 중인 피드백 · 👍 " + (", ".join(names[i] for i in fb["liked"]) or "없음")
                       + " · 👎 " + (", ".join(names[i] for i in fb["disliked"]) or "없음"))
            if st.button("피드백 초기화"):
                st.session_state.feedback = {"liked": set(), "disliked": set()}
                st.rerun()
        with st.expander(f"조건에 안 맞아서 뺀 곳 ({len(excluded)}곳)"):
            for name, why in excluded:
                st.write(f"- {name} — {why}")
