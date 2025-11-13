# blog_selenium_server.py
# FastAPI 로 JSON(title, body)을 받아 네이버 블로그에 자동 게시
# ✅ 로그인은 최초 요청 시에만 자동 수행됨 (대화 입력 시 실행)

import os
import time
import pyperclip
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ─────────────────────────────
# 환경 변수 로드 (.env)
# ─────────────────────────────
load_dotenv()
NAV_ID = os.getenv("NAVER_ID")
NAV_PW = os.getenv("NAVER_PW")

BLOG_WRITE_URL = "https://blog.naver.com/GoBlogWrite.naver"
WAIT_TIME = 15


# ─────────────────────────────
# FastAPI 앱 생성
# ─────────────────────────────
app = FastAPI()

driver = None
wait = None


# ─────────────────────────────
# 드라이버 초기화 (필요 시 실행)
# ─────────────────────────────
def init_driver():
    """ChromeDriver 초기화 (창 자동 유지 및 경고 숨김)"""
    opts = Options()
    opts.add_experimental_option("detach", True)
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # ✅ Service 객체 명시적으로 지정 (버전 충돌 방지)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1600, 950)
    return driver


# ─────────────────────────────
# 네이버 로그인
# ─────────────────────────────
def naver_login(driver: webdriver.Chrome):
    """로그인 페이지 진입 및 ID/PW 자동 입력"""
    driver.get("https://nid.naver.com/nidlogin.login")
    time.sleep(1)

    driver.find_element(By.ID, "id").click()
    pyperclip.copy(NAV_ID)
    driver.find_element(By.ID, "id").send_keys(Keys.CONTROL, "v")
    time.sleep(0.1)

    driver.find_element(By.ID, "pw").click()
    pyperclip.copy(NAV_PW)
    driver.find_element(By.ID, "pw").send_keys(Keys.CONTROL, "v")
    pyperclip.copy("")
    time.sleep(0.2)

    driver.find_element(By.ID, "log.login").click()
    time.sleep(1)
    print("✅ 로그인 완료")

    return WebDriverWait(driver, WAIT_TIME)


# ─────────────────────────────
# 블로그 글쓰기 페이지 열기
# ─────────────────────────────
def open_write_page(driver: webdriver.Chrome, wait: WebDriverWait):
    driver.get(BLOG_WRITE_URL)

    # 메인 프레임 전환
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe#mainFrame")))

    # 이어쓰기 팝업 닫기
    try:
        cancel_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-popup-button-cancel")))
        cancel_btn.click()
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".se-popup-dim")))
    except TimeoutException:
        pass

    # 도움말 패널 닫기 반복
    while True:
        try:
            driver.find_element(By.CSS_SELECTOR, ".se-help-panel-close-button").click()
            time.sleep(0.05)
        except WebDriverException:
            break


# ─────────────────────────────
# 블로그 작성
# ─────────────────────────────
def write_post(driver: webdriver.Chrome, wait: WebDriverWait, title: str, body: str):
    actions = ActionChains(driver)

    # 제목 작성
    title_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-documentTitle")))
    actions.move_to_element(title_area).click().perform()
    for ch in title:
        actions.send_keys(ch).pause(0.0001)
    actions.perform()
    actions.reset_actions()

    # 본문 작성
    body_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text")))
    actions.move_to_element(body_area).click().perform()
    for line in body.splitlines():
        for ch in line:
            actions.send_keys(ch).pause(0.0001)
        actions.send_keys(Keys.ENTER).pause(0.0001)
    actions.perform()

    print("📝 글 작성 완료")

    # 저장 (임시저장)
    try:
        save_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".save_btn__bzc5B")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_btn)
        time.sleep(0.1)
        save_btn.click()
        print("💾 임시저장 완료")
    except Exception:
        print("⚠️ 저장 버튼 클릭 실패")


# ─────────────────────────────
# 데이터 모델
# ─────────────────────────────
class PostRequest(BaseModel):
    title: str
    body: str


# ─────────────────────────────
# 헬스체크 (n8n 연결 테스트용)
# ─────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


# ─────────────────────────────
# 포스팅 실행 엔드포인트
# ─────────────────────────────
@app.post("/post-to-naver")
async def post_to_naver(req: PostRequest):
    """
    AI가 생성한 JSON(title, body)을 받아
    로그인 → 글쓰기 페이지 → 자동 입력 & 저장 수행
    """
    global driver, wait
    try:
        # 드라이버 및 로그인 확인
        if driver is None:
            driver = init_driver()
            wait = naver_login(driver)

        # 제목 자동 보정
        title = req.title.strip() if req.title.strip() else req.body.strip().split("\n")[0][:40]

        open_write_page(driver, wait)
        write_post(driver, wait, title, req.body)

        return {"status": "success", "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
