"""배포한 MoodMatch가 잠들지 않게 진짜 브라우저(헤드리스 크롬)로 들어가 본다.
잠들어 있으면 깨우기 버튼을 누르고, 앱 화면이 뜰 때까지 기다린다. 끝내 안 뜨면 실패로 끝낸다(GitHub이 메일로 알려 줌).

실행: python .github/scripts/wake_app.py [스크린샷 파일]
  주소는 환경변수 APP_URL (없으면 아래 기본값)
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "https://moodmatch-rlrtcjvhbrh76crqpv2rapp.streamlit.app/")
WAKE_TEXT = "get this app back up"  # 잠든 앱 화면의 버튼 글자 ("Yes, get this app back up!")
APP_TEXT = "오늘 기분에 꼭 맞는 곳"  # MoodMatch 첫 화면 제목
WAIT_MS = 5 * 60 * 1000  # 깨어나는 데 몇 분 걸릴 수 있다


def app_loaded(page):
    """앱은 페이지 안의 iframe에 그려지므로 모든 frame에서 제목을 찾는다."""
    return any(f.get_by_text(APP_TEXT).count() for f in page.frames)


def main():
    shot = sys.argv[1] if len(sys.argv) > 1 else None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(URL, timeout=120_000)
        page.wait_for_timeout(5000)

        wake = page.get_by_role("button", name=WAKE_TEXT)
        if wake.count():
            print("앱이 잠들어 있어서 깨우기 버튼을 눌렀어요.")
            wake.first.click()
        else:
            print("앱이 깨어 있어요.")

        waited = 0
        while not app_loaded(page) and waited < WAIT_MS:
            page.wait_for_timeout(5000)
            waited += 5000
        ok = app_loaded(page)
        if shot:
            page.wait_for_timeout(3000)
            page.screenshot(path=shot, full_page=True)
        browser.close()
    print("MoodMatch 화면이 떴어요." if ok else "MoodMatch 화면이 뜨지 않았어요!")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
