# blog_selenium_server_extended.py
# FastAPI 로 JSON(action, title, body, directive, target, replacement)을 받아
# 네이버 블로그에 글 작성 및 수정 수행

import os
import time
import pyperclip
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

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
# 환경 변수 로드 (.env)
# ─────────────────────────────
load_dotenv()
NAV_ID = os.getenv("NAVER_ID")
NAV_PW = os.getenv("NAVER_PW")

BLOG_WRITE_URL = "https://blog.naver.com/GoBlogWrite.naver"
WAIT_TIME = 15

app = FastAPI()

driver = None
wait = None


# ─────────────────────────────
# Chrome 드라이버 초기화
# ─────────────────────────────
def init_driver():
    opts = Options()
    opts.add_experimental_option("detach", True)
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1600, 950)
    return driver


# ─────────────────────────────
# 네이버 로그인
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
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe#mainFrame")))

    # 팝업 닫기
    try:
        cancel_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-popup-button-cancel")))
        cancel_btn.click()
    except TimeoutException:
        pass


# ─────────────────────────────
# 글 작성
# ─────────────────────────────
def write_post(driver: webdriver.Chrome, wait: WebDriverWait, title: str, body: str):
    actions = ActionChains(driver)

    title_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-documentTitle")))
    actions.move_to_element(title_area).click().perform()
    actions.send_keys(title).perform()

    body_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text")))
    actions.move_to_element(body_area).click().perform()
    actions.send_keys(body).perform()
    print("📝 글 작성 완료")


# ─────────────────────────────
# 내용 추가 (edit)
# ─────────────────────────────
def append_content(driver: webdriver.Chrome, wait: WebDriverWait, replacement: str):
    """기존 본문 끝에 내용 추가"""
    actions = ActionChains(driver)
    try:
        body_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text")))
        actions.move_to_element(body_area).click().perform()
        actions.send_keys(Keys.END).pause(0.2)
        actions.send_keys("\n" + replacement).perform()
        print("➕ 내용 추가 완료")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"본문 추가 실패: {e}")


# ─────────────────────────────
# 요청 데이터 모델
# ─────────────────────────────
class PostRequest(BaseModel):
    action: str
    title: Optional[str] = ""
    body: Optional[str] = None
    directive: Optional[str] = ""
    target: Optional[str] = ""
    replacement: Optional[str] = ""
    session_id: Optional[str] = None


# ─────────────────────────────
# 메인 엔드포인트
# ─────────────────────────────
@app.post("/post-to-naver")
async def post_to_naver(req: PostRequest):
    global driver, wait
    try:
        if driver is None:
            driver = init_driver()
            wait = naver_login(driver)

        if req.action == "create":
            title = req.title or req.body[:30]
            open_write_page(driver, wait)
            write_post(driver, wait, title, req.body)
            return {"status": "created", "title": title}

        elif req.action == "edit":
            append_content(driver, wait, req.replacement)
            return {"status": "appended", "added": req.replacement}

        else:
            raise HTTPException(status_code=400, detail="Invalid action type")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}
