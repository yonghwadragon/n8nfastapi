# blog_selenium_server_extended.py 
# FastAPI로 JSON(action, title, body, directive, target, replacement)을 받아
# 네이버 블로그 글 작성 및 수정 수행

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
from selenium.common.exceptions import TimeoutException, WebDriverException, ElementClickInterceptedException
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

app = FastAPI()

driver = None
wait: Optional[WebDriverWait] = None


# ─────────────────────────────
# Chrome 초기화
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
# 로그인
# ─────────────────────────────
def naver_login(driver: webdriver.Chrome):
    driver.get("https://nid.naver.com/nidlogin.login")
    time.sleep(0.6)

    driver.find_element(By.ID, "id").click()
    pyperclip.copy(NAV_ID)
    driver.find_element(By.ID, "id").send_keys(Keys.CONTROL, "v")
    time.sleep(0.1)

    driver.find_element(By.ID, "pw").click()
    pyperclip.copy(NAV_PW)
    driver.find_element(By.ID, "pw").send_keys(Keys.CONTROL, "v")
    pyperclip.copy("")
    time.sleep(0.1)

    driver.find_element(By.ID, "log.login").click()
    time.sleep(1)

    print("✅ 로그인 완료")
    return WebDriverWait(driver, WAIT_TIME)


# ─────────────────────────────
# 블로그 글쓰기 페이지 열기 (iframe + 팝업 + 도움말 닫기)
# ─────────────────────────────
def open_write_page(driver: webdriver.Chrome, wait: WebDriverWait):
    driver.get(BLOG_WRITE_URL)

    # iframe 전환
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe#mainFrame")))

    # 이어쓰기 팝업 닫기
    try:
        cancel_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-popup-button-cancel")))
        cancel_btn.click()
        time.sleep(0.1)
    except TimeoutException:
        pass

    # 도움말 패널 닫기 (여러 번 뜰 수 있음)
    while True:
        try:
            close_btn = driver.find_element(By.CSS_SELECTOR, ".se-help-panel-close-button")
            close_btn.click()
            time.sleep(0.1)
        except WebDriverException:
            break


# ─────────────────────────────
# 글 작성 (create)
# ─────────────────────────────
def write_post(driver: webdriver.Chrome, wait: WebDriverWait, title: str, body: str):
    actions = ActionChains(driver)

    # 제목 영역
    title_el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-documentTitle")))
    actions.move_to_element(title_el).click().perform()
    actions.send_keys(title).perform()
    actions.reset_actions()

    # 본문 영역
    body_el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text")))
    actions.move_to_element(body_el).click().perform()
    actions.send_keys(body).perform()

    print("📝 글 작성 완료")

    # ─────────────────────────────
    # 임시저장(저장 버튼 누르기)
    # ─────────────────────────────
    try:
        save_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".save_btn__bzc5B")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_btn)
        time.sleep(0.1)

        try:
            save_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", save_btn)

        print("💾 임시저장 완료")
    except Exception as e:
        print(f"⚠️ 임시저장 실패: {e}")

# 본문 전체를 텍스트로 읽어오는 함수
def get_current_body(driver: webdriver.Chrome, wait: WebDriverWait) -> str:
    """
    네이버 블로그 에디터의 본문 전체 텍스트를 반환
    """
    try:
        body_el = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".se-section-text"))
        )
        # innerText가 줄바꿈까지 자연스럽게 들어감
        current_text = body_el.get_attribute("innerText")
        return current_text or ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"본문 읽기 실패: {e}")

# ─────────────────────────────
# 본문 끝에 내용 추가 (append/edit)
# ─────────────────────────────
def append_content(driver: webdriver.Chrome, wait: WebDriverWait, replacement: str):
    actions = ActionChains(driver)
    try:
        body_el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text")))
        actions.move_to_element(body_el).click().perform()
        actions.send_keys(Keys.END).pause(0.2)
        actions.send_keys("\n" + replacement).perform()

        print("➕ 내용 추가 완료")

        # 내용 추가 후 자동 임시저장
        save_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".save_btn__bzc5B")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_btn)
        time.sleep(0.1)

        try:
            save_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", save_btn)

        print("💾 수정된 내용 임시저장 완료")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"본문 추가 실패: {e}")

# 본문에서 target 문장을 찾아 교체(replace) 또는 삭제(remove)
def replace_or_remove_content(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    target: str,
    replacement: str,
    mode: str,
):
    """
    mode = "replace" → target을 replacement로 1회 교체
    mode = "remove"  → target을 빈 문자열로 교체
    """
    if not target:
        raise HTTPException(status_code=400, detail="target 문장이 비어 있음")

    # 현재 본문 읽기
    current_text = get_current_body(driver, wait)

    if target not in current_text:
        raise HTTPException(
            status_code=404,
            detail="target 문장을 본문에서 찾지 못함",
        )

    if mode == "replace":
        new_text = current_text.replace(target, replacement, 1)
    elif mode == "remove":
        new_text = current_text.replace(target, "", 1)
    else:
        raise HTTPException(status_code=400, detail="invalid mode")

    # 본문 영역 선택 후 전체를 새 텍스트로 교체
    try:
        body_el = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text"))
        )
        actions = ActionChains(driver)
        actions.move_to_element(body_el).click().perform()
        # 전체 선택 후 새 텍스트 입력
        actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        actions.send_keys(new_text).perform()

        # 임시저장
        save_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".save_btn__bzc5B"))
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", save_btn
        )
        time.sleep(0.1)

        try:
            save_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", save_btn)

        print(f"✅ {mode} 적용 및 임시저장 완료")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{mode} 적용 실패: {e}")

# ─────────────────────────────
# 데이터 모델
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
# 메인 API
# ─────────────────────────────
@app.post("/post-to-naver")
async def post_to_naver(req: PostRequest):
    global driver, wait
    try:
        if driver is None:
            driver = init_driver()
            wait = naver_login(driver)

        if req.action == "create":
            title = req.title or (req.body[:30] if req.body else "새 글")
            open_write_page(driver, wait)
            write_post(driver, wait, title, req.body or "")
            return {"status": "created", "title": title}

        elif req.action == "edit":
            # directive에 따라 분기
            directive = (req.directive or "").lower()
            if directive == "append":
                append_content(driver, wait, req.replacement or "")
                return {
                    "status": "appended",
                    "added": req.replacement,
                }

            elif directive == "replace":
                replace_or_remove_content(
                    driver,
                    wait,
                    target=req.target or "",
                    replacement=req.replacement or "",
                    mode="replace",
                )
                return {
                    "status": "replaced",
                    "target": req.target,
                    "replacement": req.replacement,
                }

            elif directive == "remove":
                replace_or_remove_content(
                    driver,
                    wait,
                    target=req.target or "",
                    replacement="",
                    mode="remove",
                )
                return {
                    "status": "removed",
                    "target": req.target,
                }

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown directive: {directive}",
                )
        else:
            raise HTTPException(status_code=400, detail="Invalid action type")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/current-body")
async def current_body():
    """
    현재 에디터에 써져 있는 본문 텍스트를 반환
    - n8n에서 LLM 프롬프트에 넣어서
      '주변 문맥을 보고 이어쓰기 / 수정' 하도록 쓸 수 있음
    """
    global driver, wait
    if driver is None or wait is None:
        raise HTTPException(status_code=400, detail="드라이버가 아직 초기화되지 않음")

    try:
        # 이미 글쓰기 페이지에 들어가 있고, iframe 전환까지 된 상태라고 가정
        # 혹시 모를 상황을 위해 frame 전환을 한 번 더 시도
        try:
            driver.switch_to.default_content()
            wait.until(
                EC.frame_to_be_available_and_switch_to_it(
                    (By.CSS_SELECTOR, "iframe#mainFrame")
                )
            )
        except Exception:
            # 이미 mainFrame 안이라면 무시
            pass

        text = get_current_body(driver, wait)
        return {"body": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok"}
