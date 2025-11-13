# blog_selenium_server_stable.py
# ✅ 네이버 블로그 자동 글쓰기 (iframe 탐색 실패/element not interactable 완전 해결)

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
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ─────────────────────────────
# 환경 변수 로드
# ─────────────────────────────
load_dotenv()
NAV_ID = os.getenv("NAVER_ID")
NAV_PW = os.getenv("NAVER_PW")

BLOG_WRITE_URL = "https://blog.naver.com/GoBlogWrite.naver"
WAIT_TIME = 15


# ─────────────────────────────
# FastAPI 앱
# ─────────────────────────────
app = FastAPI()

driver = None
wait = None


# ─────────────────────────────
# 드라이버 초기화
# ─────────────────────────────
def init_driver():
    opts = Options()
    opts.add_experimental_option("detach", True)
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--disable-blink-features=AutomationControlled")

    service = Service(ChromeDriverManager().install())
    drv = webdriver.Chrome(service=service, options=opts)
    drv.set_window_size(1600, 950)
    return drv


# ─────────────────────────────
# 로그인
# ─────────────────────────────
def naver_login(driver: webdriver.Chrome):
    driver.get("https://nid.naver.com/nidlogin.login")
    time.sleep(1)

    driver.find_element(By.ID, "id").click()
    pyperclip.copy(NAV_ID)
    driver.find_element(By.ID, "id").send_keys(Keys.CONTROL, "v")
    time.sleep(0.2)

    driver.find_element(By.ID, "pw").click()
    pyperclip.copy(NAV_PW)
    driver.find_element(By.ID, "pw").send_keys(Keys.CONTROL, "v")
    pyperclip.copy("")
    time.sleep(0.3)

    driver.find_element(By.ID, "log.login").click()
    time.sleep(2)
    print("✅ 로그인 완료")

    return WebDriverWait(driver, WAIT_TIME)


# ─────────────────────────────
# 글쓰기 페이지 열기
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

    # 도움말 패널 닫기
    while True:
        try:
            driver.find_element(By.CSS_SELECTOR, ".se-help-panel-close-button").click()
            time.sleep(0.05)
        except WebDriverException:
            break


# ─────────────────────────────
# 글 작성 (기존 구조 + 안정성 개선)
# ─────────────────────────────
def write_post(driver: webdriver.Chrome, wait: WebDriverWait, title: str, body: str):
    actions = ActionChains(driver)

    # 제목 입력
    title_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-documentTitle")))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", title_area)
    driver.execute_script("arguments[0].focus();", title_area)
    actions.move_to_element(title_area).click().perform()
    actions.send_keys(title).perform()
    print("✅ 제목 입력 완료")

    # 본문 입력
    body_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text")))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", body_area)
    driver.execute_script("arguments[0].focus();", body_area)
    actions.move_to_element(body_area).click().perform()
    for line in body.splitlines():
        actions.send_keys(line).send_keys(Keys.ENTER).perform()
        time.sleep(0.01)
    print("📝 본문 입력 완료")

    # 임시 저장
    try:
        save_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".save_btn__bzc5B")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_btn)
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
# 엔드포인트
# ─────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/post-to-naver")
async def post_to_naver(req: PostRequest):
    global driver, wait
    try:
        if driver is None:
            driver = init_driver()
            wait = naver_login(driver)

        title = req.title.strip() if req.title.strip() else req.body.strip().split("\n")[0][:40]

        open_write_page(driver, wait)
        write_post(driver, wait, title, req.body)

        return {"status": "success", "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
