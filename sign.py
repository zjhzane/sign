# -*- coding: utf-8 -*-
"""
SteamTools 论坛自动登录 + dc_signin 自动签到（Playwright 优先，requests 作为可选兜底）
- 合规思路：用 Playwright 正常浏览器登录，保存 storage_state.json（登录态）
- 后续在 GitHub Actions / 服务器 headless 直接复用登录态签到
- 兼容：
  1) BOOTSTRAP=true：首次生成 storage_state.json（可 headless=false 方便人工通过验证）
  2) 正常运行：读取 storage_state.json 执行签到
环境变量：
  DC_USER / DC_PASS            账号密码（BOOTSTRAP 用）
  BASE                         站点根地址（默认 https://bbs.steamtools.net）
  EMOT_ID                      表情ID（默认 1）
  TODAY_SAY                    今日说说（默认空）
  PLAYWRIGHT_HEADLESS          true/false（默认 true；bootstrap 建议 false）
  BOOTSTRAP                    true/false（默认 false）
  STORAGE_STATE_PATH           登录态文件（默认 storage_state.json）
  DEBUG_ARTIFACTS              true/false（默认 false，保存 debug html/screenshot）
"""

import os
import re
import time
import random
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError

BASE = os.getenv("BASE", "https://bbs.steamtools.net").rstrip("/")
USERNAME = os.getenv("DC_USER", "")
PASSWORD = os.getenv("DC_PASS", "")
EMOT_ID = os.getenv("EMOT_ID", "1")
TODAY_SAY = os.getenv("TODAY_SAY", "")
HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
BOOTSTRAP = os.getenv("BOOTSTRAP", "false").lower() == "true"
STATE_PATH = os.getenv("STORAGE_STATE_PATH", "storage_state.json")
DEBUG_ARTIFACTS = os.getenv("DEBUG_ARTIFACTS", "false").lower() == "true"

LOGIN_URL = f"{BASE}/member.php?mod=logging&action=login"

# Discuz 插件签到：浮层表单（常见）
SIGN_FLOAT_URL = (
    f"{BASE}/plugin.php?id=dc_signin:sign&infloat=yes&handlekey=sign&inajax=1&ajaxtarget=fwin_content_sign"
)
# Discuz 插件签到：普通页（兜底）
SIGN_NORMAL_URL = f"{BASE}/plugin.php?id=dc_signin"


def _save_debug(page, tag: str):
    """保存调试产物：HTML + 截图"""
    if not DEBUG_ARTIFACTS:
        return
    try:
        Path("debug").mkdir(exist_ok=True)
        html_path = Path("debug") / f"{tag}.html"
        png_path = Path("debug") / f"{tag}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(png_path), full_page=True)
        print(f"🧪 已保存调试文件: {html_path} / {png_path}")
    except Exception as e:
        print(f"⚠️ 保存调试文件失败: {e}")


def _looks_like_cf_challenge(html: str) -> bool:
    """粗略判断 Cloudflare 挑战页面"""
    t = (html or "").lower()
    return (
        "cloudflare" in t
        and ("cf-chl" in t or "challenge" in t or "turnstile" in t or "verify you are human" in t)
    ) or ("/cdn-cgi/" in t)


def bootstrap_login_and_save_state():
    """
    第一次运行（建议本地/可交互环境）：
    - 打开真实浏览器（headless 建议 false）
    - 你完成可能出现的人机验证/登录
    - 保存 storage_state.json
    """
    if not USERNAME or not PASSWORD:
        raise RuntimeError("BOOTSTRAP=true 时必须提供 DC_USER / DC_PASS")

    print("============================================================")
    print("🧩 BOOTSTRAP 模式：生成登录态 storage_state.json")
    print("============================================================")
    print("站点:", BASE)
    print("登录账号:", USERNAME)
    print("Headless:", HEADLESS, "(bootstrap 建议 false)")
    print("登录态文件:", STATE_PATH)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()
        page.set_default_timeout(60000)
        page.set_default_navigation_timeout(60000)

        print("打开登录页...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        time.sleep(2)
        html = page.content()
        if _looks_like_cf_challenge(html):
            print("⚠️ 检测到可能的 Cloudflare 挑战页。请在浏览器里完成人机验证后再继续。")
            _save_debug(page, "bootstrap_cf_challenge")

        # 尝试填写（如果页面上确实存在登录表单）
        # 有些站点会在挑战完成后才显示表单，所以这里做容错
        if page.query_selector('input[name="username"]') and page.query_selector('input[name="password"]'):
            print("填写账号密码...")
            page.fill('input[name="username"]', USERNAME)
            time.sleep(random.uniform(0.4, 0.8))
            page.fill('input[name="password"]', PASSWORD)
            time.sleep(random.uniform(0.4, 0.8))

            # 点击登录（Discuz 有时候是 input[name=loginsubmit] / button）
            btn = page.query_selector('button[name="loginsubmit"], input[name="loginsubmit"]')
            if btn:
                btn.click()
            else:
                # 兜底：尝试提交表单
                page.evaluate(
                    """() => { const f=document.querySelector('form'); if(f) f.submit(); }"""
                )
        else:
            print("⚠️ 当前页面未发现登录表单。可能仍在挑战/跳转中。请在浏览器里手动完成登录。")

        print("等待登录完成（你可在浏览器里手动完成验证/登录）...")
        # 给足时间手动操作（可按需加大）
        time.sleep(20)

        # 简单判断是否已登录：页面中出现“退出/个人设置”等
        page.goto(f"{BASE}/home.php?mod=space", wait_until="domcontentloaded")
        time.sleep(2)
        html = page.content()
        _save_debug(page, "bootstrap_after_login_check")

        if ("退出" in html) or ("个人设置" in html) or ("我的" in html and "空间" in html):
            print("✅ 检测到疑似已登录状态。保存登录态...")
        else:
            print("⚠️ 未能明确检测到登录成功，但仍会保存 state（若未登录，后续会失败需重试）。")

        context.storage_state(path=STATE_PATH)
        print(f"✅ 已保存: {STATE_PATH}")

        browser.close()


def _extract_formhash(html: str) -> str | None:
    """
    从 Discuz 页面/浮层 XML CDATA 中提取 formhash
    """
    if not html:
        return None
    m = re.search(r'name=["\']formhash["\']\s+value=["\']([0-9A-Za-z]+)["\']', html)
    return m.group(1) if m else None


def sign_in_with_state():
    """
    使用已有 storage_state.json 登录态，执行 dc_signin 签到
    """
    state_file = Path(STATE_PATH)
    if not state_file.exists():
        raise RuntimeError(
            f"未找到 {STATE_PATH}。请先运行一次 BOOTSTRAP=true（建议 headless=false）生成登录态。"
        )

    print("============================================================")
    print("🚀 运行模式：加载 storage_state.json 执行签到")
    print("============================================================")
    print("站点:", BASE)
    print("登录态文件:", STATE_PATH)
    print("Headless:", HEADLESS)
    print("EMOT_ID:", EMOT_ID)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            storage_state=STATE_PATH,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        page.set_default_navigation_timeout(60000)

        # 先访问个人空间确认登录态有效
        print("检查登录态...")
        page.goto(f"{BASE}/home.php?mod=space", wait_until="domcontentloaded")
        time.sleep(2)
        html = page.content()
        if _looks_like_cf_challenge(html):
            _save_debug(page, "run_cf_challenge_on_profile")
            raise RuntimeError("出现 Cloudflare 挑战页：当前环境/IP 可能被风控，建议改自托管 runner 或重新 bootstrap。")

        if not (("退出" in html) or ("个人设置" in html) or ("我的" in html and "空间" in html)):
            _save_debug(page, "run_not_logged_in_profile")
            raise RuntimeError("登录态可能已失效（未检测到已登录标识）。请重新 BOOTSTRAP=true 生成 state。")

        print("✅ 登录态有效，开始签到...")

        # 1) 优先打开浮层签到页（很多论坛插件就是这个）
        print("打开签到浮层页...")
        page.goto(SIGN_FLOAT_URL, wait_until="domcontentloaded")
        time.sleep(2)
        html = page.content()

        if _looks_like_cf_challenge(html):
            _save_debug(page, "run_cf_challenge_on_signfloat")
            raise RuntimeError("签到页出现 Cloudflare 挑战，无法继续。")

        formhash = _extract_formhash(html)
        if not formhash:
            # 2) 兜底打开普通签到页
            print("未从浮层页获取到 formhash，尝试普通签到页...")
            page.goto(SIGN_NORMAL_URL, wait_until="domcontentloaded")
            time.sleep(2)
            html = page.content()
            formhash = _extract_formhash(html)

        if not formhash:
            _save_debug(page, "run_no_formhash")
            raise RuntimeError("无法获取 formhash（插件页面结构可能变了/需要重新适配）。")

        print("✅ formhash:", formhash[:10] + "...")

        # 3) 直接用 page.request POST 提交（更稳定，不依赖按钮选择器）
        sign_post_url = f"{BASE}/plugin.php?id=dc_signin:sign&inajax=1"
        payload = {
            "formhash": formhash,
            "signsubmit": "yes",
            "handlekey": "signin",
            "emotid": str(EMOT_ID),
            "referer": f"{BASE}/./",
            "content": TODAY_SAY,
            "signpn": "true",
        }

        print("提交签到请求...")
        resp = context.request.post(
            sign_post_url,
            form=payload,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{BASE}/./",
            },
            timeout=60000,
        )
        text = resp.text()
        if DEBUG_ARTIFACTS:
            Path("debug").mkdir(exist_ok=True)
            Path("debug") / "sign_response.txt"
            (Path("debug") / "sign_response.txt").write_text(text, encoding="utf-8")

        # 4) 判断结果（适配常见返回）
        ok = any(
            k in text
            for k in ["签到成功", "已签", "succeed", "showDialog", "success"]
        )
        already = any(
            k in text
            for k in ["今天已经签到", "您今天已经签到过了", "already"]
        )

        if ok:
            print("✅ 签到成功！")
        elif already:
            print("✅ 今天已经签到过了！")
        else:
            # 很多 Discuz AJAX 返回是 XML/CDATA 或 showDialog，结构可能不同
            print("⚠️ 未能明确匹配成功/已签到关键词，但请求已返回。建议开启 DEBUG_ARTIFACTS=true 查看响应。")
            print("响应前200字符：", text[:200])

        browser.close()


def main():
    try:
        if BOOTSTRAP:
            bootstrap_login_and_save_state()
        else:
            sign_in_with_state()
        return 0
    except (PWTimeout, PWError) as e:
        print(f"❌ Playwright 错误: {e}")
        return 1
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
