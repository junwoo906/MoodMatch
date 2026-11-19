"""MoodMatch 웹: 취향 질문지 5문항에 답하면 지금 갈 수 있는 팝업·전시·카페 Top 3를 추천한다.

실행: streamlit run demo/app.py
"""
from datetime import date

import streamlit as st

import recommend as rec

TYPES = ["팝업", "전시", "카페"]
ACTIVITIES = ["체험", "사진", "굿즈", "관람", "음식"]
MOODS = ["귀여운", "조용한", "트렌디", "예술적", "레트로"]
COMPANIONS = ["혼자", "친구", "연인", "가족"]
BUDGETS = {"무료만": 0, "5천 원": 5000, "1만 원": 10000, "2만 원": 20000, "3만 원": 30000, "상관없음": 10**9}
TYPE_ICON = {"팝업": "🛍️", "전시": "🖼️", "카페": "☕"}


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
        st.markdown(f"### {rank}. {TYPE_ICON.get(p['type'], '')} {p['name']}")
        price = "가격 미확인" if p["price"] is None else ("무료" if p["price"] == 0 else f"{p['price']:,}원")
        st.caption(f"{p['type']} · {p['region']} · {price} · {period_text(p)}")
        st.markdown(f"**추천 이유:** {reason_text(best)} (점수 {score:.2f})")
        st.write(p["desc"])
        if p.get("source"):
            st.markdown(f"[공식 안내 보기]({p['source']})")
        fb = st.session_state.feedback
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button("👍 좋아요", key=f"like{p['id']}", disabled=p["id"] in fb["liked"]):
            fb["liked"].add(p["id"])
            st.rerun()
        if c2.button("👎 별로예요", key=f"dislike{p['id']}"):
            fb["disliked"].add(p["id"])
            fb["liked"].discard(p["id"])
            st.rerun()


st.set_page_config(page_title="MoodMatch", page_icon="🎈")
st.title("🎈 MoodMatch")
st.write("취향 질문 몇 개에 답하면, 지금 갈 수 있는 팝업·전시·카페를 추천해 드려요.")

model, places, place_vecs = load()
if "feedback" not in st.session_state:
    st.session_state.feedback = {"liked": set(), "disliked": set()}
if "answers" not in st.session_state:
    st.session_state.answers = None

with st.form("survey"):
    types = st.multiselect("Q1. 어디에 가고 싶어요? (여러 개)", TYPES, default=TYPES)
    activity = st.multiselect("Q2. 가서 뭘 하고 싶어요? (고른 순서대로 1~3순위)", ACTIVITIES, max_selections=3)
    mood = st.multiselect("Q3. 원하는 분위기는? (고른 순서대로 1~3순위)", MOODS, max_selections=3)
    with_ = st.radio("Q4. 누구랑 가요?", COMPANIONS, horizontal=True)
    st.markdown("**Q5. 언제, 어디서, 얼마까지?**")
    c1, c2 = st.columns(2)
    day = c1.date_input("방문 날짜", value=date.today(), min_value=date.today())
    budget = c2.select_slider("1인 예산", options=list(BUDGETS), value="1만 원")
    regions = st.multiselect("지역 (비워 두면 전체)", sorted({p["region"] for p in places}))
    submitted = st.form_submit_button("추천받기", type="primary", use_container_width=True)

if submitted:
    if not types or not activity or not mood:
        st.warning("Q1~Q3는 하나 이상 골라 주세요.")
        st.session_state.answers = None
    else:
        st.session_state.answers = {
            "types": types, "activity_rank": activity, "mood_rank": mood, "with": with_,
            "date": day.isoformat(), "regions": regions or None, "budget": BUDGETS[budget],
        }

ans = st.session_state.answers
if ans:
    fb = st.session_state.feedback
    top, excluded = rec.recommend(model, places, ans, place_vecs=place_vecs,
                                  liked=fb["liked"], disliked=fb["disliked"])
    st.subheader("추천 결과")
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
