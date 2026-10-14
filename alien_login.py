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
    page.wait_for_timeout(1500)

    dismiss_onboarding(page)
    open_login_dialog(page)
    fill_login_form(page, phone, password)
    submit_login(page)
    wait_login_success(page)


def ensure_active(page) -> None:
    """登录后检查 header 活跃度状态。

    注意（2026-10-14 实测）：活跃度验证不是页内按钮确认流程。点击
    「今日未活跃」只会弹出「请完成活跃验证」说明弹窗，里面没有任何
    确认/开始按钮；真正的激活方式是启动 PC 端或手机端外星仔加速器并
    登录同一账号，启动后 1-3 分钟完成验证。因此脚本无法在网页上
    自己完成激活：已活跃就继续，未活跃就明确报错退出。
    """
    if page.get_by_text("今日已活跃", exact=False).count() > 0:
        print("账号今日已活跃。")
        return
    raise PlaywrightTimeout(
        "账号今日未活跃：需先启动外星仔加速器客户端（PC 端或手机端）"
        "并登录同一账号，启动后 1-3 分钟完成验证；网页上无法直接激活。"
    )


def click_game_card(page, game_titles: list[str]):
    """按顺序尝试点击游戏卡片，优先点击「进行中」区域的第一个卡片。"""
    last_error: Exception | None = None
    for title in game_titles:
        try:
            # 优先在「进行中」区域定位，且加上 .first 确保只点第一个，避免与「已结束」冲突
            ongoing = page.get_by_label("进行中")
            if ongoing.count() > 0 and ongoing.get_by_role("heading", name=title, level=4, exact=True).count() > 0:
                card = ongoing.get_by_role("heading", name=title, level=4, exact=True).first
            else:
                card = page.get_by_role("heading", name=title, level=4, exact=True).first

            card.wait_for(state="visible", timeout=5000)
            card.click()
            return title
        except Exception as exc:
            last_error = exc
            print(f"未找到「{title}」，尝试下一个...")
    titles = "、".join(game_titles)
    print(f"未找到游戏卡片，已尝试：{titles}")
    return None


def click_first_join_button(page) -> None:
    """只点击列表中的第一个参加按钮，而不是全部参加。"""
    button_selectors = [
        page.get_by_role("button", name="参加", exact=True),
        page.get_by_role("button", name="立即参加", exact=True),
        page.locator("button").filter(has_text=re.compile(r"^(参加|立即参加)$")),
        page.locator("button").filter(has_text="参加"),
        page.get_by_role("button", name="全部参加", exact=True),
    ]
    for locator in button_selectors:
        if locator.count() > 0:
            btn = locator.first
            btn.wait_for(state="visible", timeout=10000)
            btn.click()
            page.wait_for_timeout(1500)
            return

    raise PlaywrightTimeout("未找到可点击的参加按钮")


def search_and_join_game(page, keyword: str, game_titles: list[str]) -> str:
    """搜索游戏并点击第一个参加按钮。"""
    search_box = page.get_by_placeholder("搜索游戏...")
    search_box.wait_for(state="visible", timeout=10000)
    search_box.fill(keyword)
    page.wait_for_timeout(800)

    matched_title = click_game_card(page, game_titles)
    if matched_title is None:
        return None
    page.wait_for_timeout(1000)

    click_first_join_button(page)
    return matched_title


def safe_wait() -> None:
    """非无头模式下的安全退出等待，避免在非交互环境下抛出 EOFError。"""
    if not HEADLESS:
        try:
            input("按 Enter 关闭浏览器...")
        except (EOFError, KeyboardInterrupt):
            pass


def main() -> int:
    if not PHONE or not PASSWORD or not SEARCH_KEYWORD or not GAME_TITLES:
        print("请在脚本顶部配置区填写 PHONE、PASSWORD、SEARCH_KEYWORD、GAME_TITLES。")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            locale="zh-CN",
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()

        try:
            login(page, PHONE, PASSWORD)
            print("登录成功！")

            ensure_active(page)

            matched = search_and_join_game(page, SEARCH_KEYWORD, GAME_TITLES)
            if matched is None:
                print(f"当前没有可参加的 {SEARCH_KEYWORD} 活动，正常退出。")
                return 0
            print(f"已搜索 {SEARCH_KEYWORD} 并点击第一个参加按钮：{matched}")

            safe_wait()
            return 0
        except PlaywrightTimeout as exc:
            print(f"操作超时或失败：{exc}")
            safe_wait()
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
