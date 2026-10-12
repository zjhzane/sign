import os
import re
import sys


from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


URL = "https://drops.et001.com/campaigns/"


# ========== 配置区 ==========
# 账号密码从环境变量读取（GitHub Actions 里对应 Secrets: ALIEN_PHONE / ALIEN_PASSWORD），
# 不要把明文密码写进代码或提交到公开仓库。
PHONE = os.environ.get("ALIEN_PHONE", "")
PASSWORD = os.environ.get("ALIEN_PASSWORD", "")
SEARCH_KEYWORD = "炉石传说"
# 按顺序尝试，需与页面上 h4 标题完全一致
GAME_TITLES = ["炉石传说 国际服", "Hearthstone", "炉石传说"]
# 无头模式：True=后台运行，False=显示浏览器（定时任务请设为 True）
# 可通过环境变量 HEADLESS=true 覆盖（GitHub Actions 定时任务用）
HEADLESS = os.environ.get("HEADLESS", "false").strip().lower() == "true"
# ============================================




def dismiss_onboarding(page) -> None:
    """关闭首次访问的引导弹窗。"""
    skip_btn = page.get_by_role("button", name="Skip / 跳过")
    if skip_btn.count() > 0:
        skip_btn.first.click(timeout=3000)
        page.wait_for_timeout(500)




def open_login_dialog(page) -> None:
    """点击右上角「登录」打开登录弹窗。"""
    page.get_by_text("登录", exact=True).first.click()
    page.get_by_role("heading", name="请先登录").wait_for(state="visible", timeout=10000)




def fill_login_form(page, phone: str, password: str) -> None:
    """填写手机号、密码并勾选免责声明。"""
    page.get_by_placeholder("请输入手机号").fill(phone)
    page.get_by_placeholder("请输入密码").fill(password)


    # 勾选「使用本服务即代表您同意《外星仔免责声明》」
    agree_label = page.get_by_text("使用本服务即代表您同意", exact=False)
    agree_label.wait_for(state="visible", timeout=5000)
    agree_label.locator("xpath=preceding-sibling::button[1]").click()




def submit_login(page) -> None:
    """点击弹窗内的登录按钮。"""
    login_btn = page.locator("button").filter(has_text="登录").last
    login_btn.wait_for(state="visible", timeout=5000)
    login_btn.click()




def wait_login_success(page) -> None:
    """等待登录弹窗关闭，且右上角不再显示「登录」。"""
    page.get_by_role("heading", name="请先登录").wait_for(state="hidden", timeout=15000)
    page.get_by_text("登录", exact=True).first.wait_for(state="hidden", timeout=15000)




def login(page, phone: str, password: str) -> None:
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
