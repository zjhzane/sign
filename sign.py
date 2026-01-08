# -*- coding: utf-8 -*-
"""
使用 requests + cloudflare-scraper 的版本（推荐）
"""

import os
import time
import random
import re
from bs4 import BeautifulSoup
# 尝试导入 cloudflare-scraper，如果没有则使用 requests
try:
    import cloudscraper
    import requests  # cloudscraper 基于 requests，确保可以访问 requests.exceptions
    HAS_CLOUDSCRAPER = True
    print("✅ 使用 cloudflare-scraper")
except ImportError:
    try:
        import requests

        HAS_CLOUDSCRAPER = False
        print("⚠️ cloudflare-scraper 未安装，使用 requests（可能无法绕过 Cloudflare）")
        print("   建议安装: pip install cloudscraper")
    except ImportError:
        raise ImportError("请安装 requests 或 cloudscraper: pip install requests cloudscraper")

# 如果使用 Playwright 版本，需要导入
USE_PLAYWRIGHT = os.getenv("USE_PLAYWRIGHT", "false").lower() == "true"
if USE_PLAYWRIGHT:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, Error as PlaywrightError
    except ImportError:
        print("⚠️ Playwright 未安装，将使用 requests 版本")
        USE_PLAYWRIGHT = False

USERNAME = os.getenv("DC_USER")
PASSWORD = os.getenv("DC_PASS")

if not USERNAME or not PASSWORD:
    raise RuntimeError("账号或密码未配置，请在 GitHub Secrets 里设置 DC_USER / DC_PASS")

print("准备登录账号:", USERNAME)

BASE = "https://bbs.steamtools.net"
EMOT_ID = "1"
TODAY_SAY = ""


def get_session():
    """创建会话（使用 cloudflare-scraper 或 requests）"""
    if HAS_CLOUDSCRAPER:
        session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
    else:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    # 限制最大重定向次数，避免重定向循环
    session.max_redirects = 10
    return session


def login_with_requests(session, username, password, max_retries=3):
    """使用 requests 登录"""
    for attempt in range(max_retries):
        try:
            print(f"访问登录页面 (尝试 {attempt + 1}/{max_retries})...")
            
            # 在请求前添加延迟，避免触发速率限制
            if attempt > 0:
                wait_time = min(30 * (2 ** attempt), 300)  # 指数退避，最多等待5分钟
                print(f"等待 {wait_time} 秒后重试（避免速率限制）...")
                time.sleep(wait_time)
            else:
                # 首次请求也添加随机延迟
                time.sleep(random.uniform(2, 5))

            # 1. 访问登录页面获取 formhash
            login_url = f"{BASE}/member.php?mod=logging&action=login"
            try:
                response = session.get(login_url, timeout=30, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # 429 错误：请求过于频繁
                    retry_after = int(e.response.headers.get('Retry-After', 60))
                    print(f"⚠️ 收到 429 错误，需要等待 {retry_after} 秒...")
                    if attempt < max_retries - 1:
                        wait_time = max(retry_after, 60)  # 至少等待60秒
                        print(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                else:
                    raise
            except requests.exceptions.TooManyRedirects:
                print("⚠️ 重定向次数过多，可能是重定向循环")
                if attempt < max_retries - 1:
                    wait_time = 30 * (attempt + 1)
                    print(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise

            # 解析 formhash
            soup = BeautifulSoup(response.text, 'html.parser')
            formhash_input = soup.find('input', {'name': 'formhash'})
            if not formhash_input:
                # 尝试从 HTML 中正则提取
                formhash_match = re.search(r'name=["\']formhash["\']\s+value=["\']([0-9A-Za-z]+)["\']', response.text)
                if formhash_match:
                    formhash = formhash_match.group(1)
                else:
                    print("⚠️ 无法获取 formhash")
                    if attempt < max_retries - 1:
                        time.sleep(3)
                        continue
                    raise RuntimeError("无法获取 formhash")
            else:
                formhash = formhash_input.get('value')

            print(f"✅ 获取到 formhash: {formhash[:10]}...")

            # 2. 提交登录表单
            print("提交登录表单...")
            # 在提交前添加延迟
            time.sleep(random.uniform(1, 3))
            
            login_action_url = f"{BASE}/member.php?mod=logging&action=login&loginsubmit=yes&inajax=1"

            login_data = {
                'formhash': formhash,
                'referer': f"{BASE}/./",
                'username': username,
                'password': password,
                'questionid': '0',
                'answer': '',
                'cookietime': '2592000',  # 自动登录
                'loginsubmit': 'true'
            }

            try:
                response = session.post(login_action_url, data=login_data, timeout=30, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 60))
                    print(f"⚠️ 提交登录时收到 429 错误，需要等待 {retry_after} 秒...")
                    if attempt < max_retries - 1:
                        wait_time = max(retry_after, 60)
                        print(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                else:
                    raise

            # 3. 检查登录是否成功
            if "欢迎您回来" in response.text or "登录成功" in response.text or "succeed" in response.text.lower():
                print("✅ 登录成功！")
                return True
            elif "密码错误" in response.text or "用户名不存在" in response.text:
                print("❌ 登录失败：用户名或密码错误")
                return False
            else:
                # 检查当前页面是否已登录
                profile_url = f"{BASE}/home.php?mod=space"
                response = session.get(profile_url, timeout=30)
                if "退出" in response.text or "个人设置" in response.text:
                    print("✅ 登录成功（通过检查个人页面确认）！")
                    return True

                print(f"⚠️ 登录结果不确定，响应: {response.text[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                return False

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get('Retry-After', 60))
                print(f"⚠️ 收到 429 错误 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait_time = max(retry_after, 60)
                    print(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
            print(f"⚠️ HTTP 错误 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = min(30 * (2 ** attempt), 300)
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            import traceback
            traceback.print_exc()
            return False
        except requests.exceptions.TooManyRedirects as e:
            print(f"⚠️ 重定向次数过多 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = 30 * (attempt + 1)
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            import traceback
            traceback.print_exc()
            return False
        except Exception as e:
            print(f"⚠️ 登录过程出错 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = min(30 * (2 ** attempt), 300)
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            import traceback
            traceback.print_exc()
            return False

    return False


def sign_with_requests(session, emotid="1", today_say="", max_retries=3):
    """使用 requests 签到"""
    for attempt in range(max_retries):
        try:
            print(f"访问签到页面 (尝试 {attempt + 1}/{max_retries})...")
            
            # 在请求前添加延迟
            if attempt > 0:
                wait_time = min(30 * (2 ** attempt), 300)
                print(f"等待 {wait_time} 秒后重试（避免速率限制）...")
                time.sleep(wait_time)
            else:
                time.sleep(random.uniform(2, 5))

            # 使用您提供的签到 URL（获取表单）
            sign_url = f"{BASE}/plugin.php?id=dc_signin:sign&infloat=yes&handlekey=sign&inajax=1&ajaxtarget=fwin_content_sign"

            try:
                response = session.get(sign_url, timeout=30)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 60))
                    print(f"⚠️ 收到 429 错误，需要等待 {retry_after} 秒...")
                    if attempt < max_retries - 1:
                        wait_time = max(retry_after, 60)
                        print(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                else:
                    raise

            # 解析 formhash（可能需要从 XML/CDATA 中提取）
            formhash = None

            # 方法1: 尝试从 CDATA 中提取（因为响应是 XML 格式）
            cdata_match = re.search(r'name=["\']formhash["\']\s+value=["\']([0-9A-Za-z]+)["\']', response.text)
            if cdata_match:
                formhash = cdata_match.group(1)
                print(f"✅ 从 CDATA 中获取到 formhash: {formhash[:10]}...")
            else:
                # 方法2: 尝试用 BeautifulSoup 解析（如果是 HTML）
                try:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    formhash_input = soup.find('input', {'name': 'formhash'})
                    if formhash_input:
                        formhash = formhash_input.get('value')
                        print(f"✅ 从 HTML 中获取到 formhash: {formhash[:10]}...")
                except:
                    pass

                # 方法3: 尝试正则提取（通用方法）
                if not formhash:
                    formhash_match = re.search(r'name=["\']formhash["\']\s+value=["\']([0-9A-Za-z]+)["\']',
                                               response.text)
                    if formhash_match:
                        formhash = formhash_match.group(1)
                        print(f"✅ 通过正则提取到 formhash: {formhash[:10]}...")

            if not formhash:
                print("⚠️ 无法获取签到 formhash")
                print(f"调试信息 - 响应前200字符: {response.text[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                raise RuntimeError("无法获取签到 formhash")

            # 提交签到表单（根据 XML 中的表单结构）
            print(f"提交签到（表情 ID: {emotid}）...")
            # 在提交前添加延迟
            time.sleep(random.uniform(1, 3))
            
            # 表单 action: plugin.php?id=dc_signin:sign
            # 使用 AJAX 方式提交（inajax=1）
            sign_action_url = f"{BASE}/plugin.php?id=dc_signin:sign&inajax=1"

            # 根据 XML 中的表单字段，需要包含所有必需字段
            sign_data = {
                'formhash': formhash,
                'signsubmit': 'yes',  # XML 中显示需要这个字段
                'handlekey': 'signin',  # XML 中显示需要这个字段
                'emotid': emotid,
                'referer': f"{BASE}/./",  # XML 中显示需要这个字段
                'content': today_say,  # 今日说说（可选）
                'signpn': 'true'  # 提交按钮
            }

            # 设置 AJAX 请求头
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f"{BASE}/./"
            }

            try:
                response = session.post(sign_action_url, data=sign_data, headers=headers, timeout=30)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 60))
                    print(f"⚠️ 提交签到时收到 429 错误，需要等待 {retry_after} 秒...")
                    if attempt < max_retries - 1:
                        wait_time = max(retry_after, 60)
                        print(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                else:
                    raise

            # 检查签到结果（可能需要检查 XML 响应）
            response_text = response.text

            # 检查是否成功
            if ("签到成功" in response_text or
                    "已签" in response_text or
                    "succeed" in response_text.lower() or
                    "succeedhandle_signin" in response_text or
                    "showDialog" in response_text):
                print("✅ 签到成功！")
                return True
            elif ("今天已经签到" in response_text or
                  "already" in response_text.lower() or
                  "您今天已经签到过了" in response_text):
                print("✅ 今天已经签到过了！")
                return True
            else:
                print(f"⚠️ 签到结果不确定，响应: {response_text[:500]}")
                # 如果响应包含 XML 结构但没有错误信息，可能是成功
                if "CDATA" in response_text or "xml" in response_text.lower():
                    print("⚠️ 收到 XML 响应，尝试解析...")
                    # 可能是成功的响应，返回 True
                    return True
                return True  # 即使不确定也返回 True，可能是已签到的情况

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get('Retry-After', 60))
                print(f"⚠️ 收到 429 错误 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait_time = max(retry_after, 60)
                    print(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
            print(f"⚠️ HTTP 错误 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = min(30 * (2 ** attempt), 300)
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            import traceback
            traceback.print_exc()
            return False
        except Exception as e:
            print(f"⚠️ 签到过程出错 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = min(30 * (2 ** attempt), 300)
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            import traceback
            traceback.print_exc()
            return False

    return False


def login_with_playwright(page, username, password, max_retries=3):
    """使用 Playwright 登录，带重试机制"""
    for attempt in range(max_retries):
        try:
            print(f"访问登录页面 (尝试 {attempt + 1}/{max_retries})...")

            # 使用更灵活的等待策略，避免 ERR_NETWORK_CHANGED
            try:
                # 先尝试使用 domcontentloaded（更快，更稳定）
                page.goto(
                    f"{BASE}/member.php?mod=logging&action=login",
                    wait_until="domcontentloaded",
                    timeout=60000
                )
            except PlaywrightError as e:
                if "ERR_NETWORK_CHANGED" in str(e) or "net::ERR" in str(e):
                    print(f"⚠️ 网络错误 (尝试 {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        print(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    raise
                else:
                    raise

            # 等待页面加载
            time.sleep(random.uniform(2, 4))

            # 等待 Cloudflare 挑战完成（如果有）
            print("等待页面加载完成...")
            try:
                # 等待网络空闲，但使用更长的超时
                page.wait_for_load_state("networkidle", timeout=30000)
            except:
                # 如果 networkidle 失败，至少等待 DOM 加载完成
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except:
                    pass

            # 快速检查 Cloudflare 挑战（缩短等待时间）
            print("检查 Cloudflare 挑战...")
            max_cf_wait = 20  # 缩短到 20 秒
            cf_wait_count = 0
            last_url = page.url

            # 先快速检查一次
            time.sleep(2)
            page_content = page.content()
            has_login_form = page.query_selector('input[name="username"]') is not None
            is_cf_challenge = (
                    "cloudflare" in page_content.lower() and
                    (
                            "cf-chl" in page_content.lower() or
                            "turnstile" in page_content.lower() or
                            "verify you are human" in page_content.lower()
                    )
            )

            # 如果已经有登录表单，直接跳过等待
            if has_login_form and not is_cf_challenge:
                print("✅ 登录表单已存在，跳过 Cloudflare 挑战等待")
            elif is_cf_challenge:
                # 只有在确实有挑战时才等待
                print("⚠️ 检测到 Cloudflare 挑战，等待最多 20 秒...")
                while cf_wait_count < max_cf_wait:
                    try:
                        current_url = page.url
                        page_content = page.content()

                        # 检查登录表单是否已经出现
                        has_login_form = page.query_selector('input[name="username"]') is not None
                        if has_login_form:
                            print("✅ 登录表单已加载")
                            break

                        # 检查是否还在挑战中
                        is_cf_challenge = (
                                "cloudflare" in page_content.lower() and
                                (
                                        "cf-chl" in page_content.lower() or
                                        "turnstile" in page_content.lower() or
                                        "verify you are human" in page_content.lower()
                                )
                        )

                        if not is_cf_challenge and has_login_form:
                            print("✅ Cloudflare 挑战完成")
                            break

                        # 检查 URL 变化
                        if current_url != last_url and "member.php?mod=logging" in current_url:
                            time.sleep(2)
                            has_login_form = page.query_selector('input[name="username"]') is not None
                            if has_login_form:
                                print("✅ 通过 URL 变化检测到登录表单")
                                break

                        last_url = current_url
                        time.sleep(2)
                        cf_wait_count += 2

                        if cf_wait_count % 6 == 0:
                            print(f"⚠️ 等待中... ({cf_wait_count}/{max_cf_wait} 秒)")

                    except Exception as e:
                        print(f"⚠️ 检查时出错: {e}")
                        time.sleep(2)
                        cf_wait_count += 2

                if cf_wait_count >= max_cf_wait:
                    print("⚠️ Cloudflare 挑战等待超时，直接尝试登录...")

            # 快速确认登录表单是否存在（降低超时时间）
            print("确认登录表单...")
            username_input = None

            # 方法1: 快速尝试查找（只等 5 秒）
            try:
                username_input = page.wait_for_selector('input[name="username"]', timeout=5000, state='visible')
                print("✅ 登录表单已确认存在")
            except:
                pass

            # 方法2: 直接查找（不等待）
            if not username_input:
                try:
                    username_input = page.query_selector('input[name="username"]')
                    if username_input:
                        print("✅ 找到登录表单")
                except:
                    pass

            # 方法3: 如果仍然找不到，尝试重新加载页面（最多重试 1 次）
            if not username_input and attempt < max_retries:
                print("⚠️ 登录表单未找到，尝试重新访问登录页面...")
                try:
                    page.goto(
                        f"{BASE}/member.php?mod=logging&action=login",
                        wait_until="domcontentloaded",
                        timeout=20000
                    )
                    time.sleep(3)  # 缩短等待时间
                    username_input = page.query_selector('input[name="username"]')
                    if username_input:
                        print("✅ 通过重新访问找到登录表单")
                    else:
                        print("⚠️ 重新访问后仍未找到登录表单，但尝试继续...")
                        # 保存调试信息
                        try:
                            with open(f"cf_challenge_debug_{attempt}.html", "w", encoding="utf-8") as f:
                                f.write(page.content())
                            print(f"已保存调试文件: cf_challenge_debug_{attempt}.html")
                        except:
                            pass
                except Exception as retry_e:
                    print(f"⚠️ 重新访问失败: {retry_e}")

            # 如果还是找不到，但这是最后一次尝试，直接报错
            if not username_input and attempt == max_retries - 1:
                raise RuntimeError("无法找到登录表单，可能被 Cloudflare 拦截")
            elif not username_input:
                print("⚠️ 未找到登录表单，重试中...")
                time.sleep(3)
                continue

            # 填写用户名
            print("填写用户名...")
            try:
                # 如果之前没有找到，再次查找
                if not username_input:
                    username_input = page.wait_for_selector('input[name="username"]', timeout=20000, state='visible')

                username_input.fill(username)
                time.sleep(random.uniform(0.5, 1))
            except Exception as e:
                print(f"⚠️ 填写用户名失败: {e}")
                if attempt < max_retries - 1:
                    continue
                raise

            # 填写密码
            print("填写密码...")
            try:
                password_input = page.wait_for_selector('input[name="password"]', timeout=20000)
                password_input.fill(password)
                time.sleep(random.uniform(0.5, 1))
            except Exception as e:
                print(f"⚠️ 填写密码失败: {e}")
                if attempt < max_retries - 1:
                    continue
                raise

            # 获取 formhash（通过 JavaScript 执行）
            print("获取 formhash...")
            formhash = page.evaluate("""
                () => {
                    var input = document.querySelector('input[name="formhash"]');
                    return input ? input.value : null;
                }
            """)

            if not formhash:
                # 尝试直接获取
                formhash_input = page.query_selector('input[name="formhash"]')
                if formhash_input:
                    formhash = formhash_input.get_attribute("value")

            if not formhash:
                print("⚠️ 无法获取 formhash")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise RuntimeError("无法获取 formhash")

            print(f"✅ 获取到 formhash: {formhash[:10]}...")

            # 提交登录表单
            print("提交登录表单...")
            login_button = page.query_selector('button[name="loginsubmit"], input[name="loginsubmit"]')
            if login_button:
                login_button.click()
            else:
                # 尝试通过表单提交
                page.evaluate("""
                    () => {
                        var form = document.querySelector('form');
                        if (form) form.submit();
                    }
                """)

            # 等待登录完成
            time.sleep(random.uniform(3, 5))

            # 等待页面跳转或内容更新
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except:
                pass

            # 检查登录是否成功
            page_content = page.content()
            if "欢迎您回来" in page_content or "登录成功" in page_content:
                print("✅ 登录成功！")
                return True
            else:
                print(f"⚠️ 登录可能失败，检查页面内容...")
                # 保存页面内容用于调试
                try:
                    with open("login_debug.html", "w", encoding="utf-8") as f:
                        f.write(page_content)
                    print("已保存调试文件: login_debug.html")
                except:
                    pass

                if attempt < max_retries - 1:
                    print(f"重试登录...")
                    time.sleep(5)
                    continue
                return False

        except PlaywrightTimeout as e:
            print(f"⚠️ 超时错误 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return False
        except PlaywrightError as e:
            error_str = str(e)
            if "ERR_NETWORK_CHANGED" in error_str or "net::ERR" in error_str:
                print(f"⚠️ 网络错误 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    print(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
            raise
        except Exception as e:
            print(f"⚠️ 登录过程出错 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            import traceback
            traceback.print_exc()
            return False

    return False


def sign_with_playwright(page, max_retries=3):
    """使用 Playwright 签到，带重试机制"""
    for attempt in range(max_retries):
        try:
            print(f"访问签到页面 (尝试 {attempt + 1}/{max_retries})...")
            # 方法1: 尝试从 XML 格式的签到表单获取
            sign_url = f"{BASE}/plugin.php?id=dc_signin:sign&infloat=yes&handlekey=sign&inajax=1&ajaxtarget=fwin_content_sign"

            try:
                page.goto(sign_url, wait_until="domcontentloaded", timeout=60000)
            except PlaywrightError as e:
                if "ERR_NETWORK_CHANGED" in str(e) or "net::ERR" in str(e):
                    print(f"⚠️ 网络错误 (尝试 {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3
                        print(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    raise
                else:
                    raise

            time.sleep(random.uniform(2, 3))

            # 等待页面加载
            try:
                page.wait_for_load_state("domcontentloaded", timeout=20000)
            except:
                pass

            # 通过 JavaScript 获取 formhash
            print("获取签到 formhash...")
            formhash = page.evaluate("""
                () => {
                    var input = document.querySelector('input[name="formhash"]');
                    return input ? input.value : null;
                }
            """)

            if not formhash:
                # 尝试从 XML/CDATA 中提取
                page_content = page.content()
                import re
                cdata_match = re.search(r'name=["\']formhash["\']\s+value=["\']([0-9A-Za-z]+)["\']', page_content)
                if cdata_match:
                    formhash = cdata_match.group(1)

            if not formhash:
                # 尝试从常规签到页面获取
                print("尝试从常规签到页面获取 formhash...")
                try:
                    page.goto(f"{BASE}/plugin.php?id=dc_signin&mobile=no", wait_until="domcontentloaded", timeout=60000)
                    time.sleep(2)
                    formhash = page.evaluate("""
                        () => {
                            var input = document.querySelector('input[name="formhash"]');
                            return input ? input.value : null;
                        }
                    """)
                except Exception as e:
                    print(f"⚠️ 访问常规签到页面失败: {e}")

            if not formhash:
                print("⚠️ 无法获取签到 formhash")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise RuntimeError("无法获取签到 formhash")

            print(f"✅ 获取到签到 formhash: {formhash[:10]}...")

            # 选择表情（通过 JavaScript）
            print(f"选择表情 ID: {EMOT_ID}...")
            page.evaluate(f"""
                () => {{
                    var emotidInput = document.querySelector('input[name="emotid"]');
                    if (emotidInput) {{
                        emotidInput.value = '{EMOT_ID}';
                    }}
                    // 触发表情选择
                    var emotLi = document.querySelector('li[onclick*="check(this, {EMOT_ID})"]');
                    if (emotLi) {{
                        emotLi.click();
                    }}
                }}
            """)

            time.sleep(random.uniform(1, 2))

            # 填写今日说说（如果有）
            if TODAY_SAY:
                print("填写今日说说...")
                content_textarea = page.query_selector('textarea[name="content"]')
                if content_textarea:
                    content_textarea.fill(TODAY_SAY)
                    time.sleep(random.uniform(0.5, 1))

            # 提交签到表单
            print("提交签到...")
            submit_button = page.query_selector('button[name="signpn"], input[name="signpn"]')
            if submit_button:
                submit_button.click()
            else:
                # 尝试通过表单提交
                page.evaluate("""
                    () => {
                        var form = document.querySelector('form#signform');
                        if (form) form.submit();
                    }
                """)

            # 等待响应
            time.sleep(random.uniform(2, 3))

            # 检查签到结果
            page_content = page.content()
            if "签到成功" in page_content or "已签" in page_content or "succeed" in page_content.lower():
                print("✅ 签到成功！")
                return True
            else:
                print(f"⚠️ 签到结果不确定，响应: {page_content[:500]}")
                return True  # 可能是已签到的情况

        except PlaywrightError as e:
            error_str = str(e)
            if "ERR_NETWORK_CHANGED" in error_str or "net::ERR" in error_str:
                print(f"⚠️ 网络错误 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3
                    print(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
            else:
                print(f"⚠️ Playwright 错误 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
            raise
        except Exception as e:
            print(f"⚠️ 签到过程出错 (尝试 {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            import traceback
            traceback.print_exc()
            return False

    return False


def main():
    """主函数：优先使用 requests 版本，如果需要 Playwright 则设置环境变量 USE_PLAYWRIGHT=true"""
    should_try_playwright = False
    
    # 优先使用 requests 版本（更快更简单）
    if not USE_PLAYWRIGHT:
        try:
            print("=" * 60)
            print("🚀 使用 requests + cloudflare-scraper 版本")
            print("=" * 60)

            # 创建会话
            session = get_session()

            # 登录
            if not login_with_requests(session, USERNAME, PASSWORD):
                raise RuntimeError("登录失败")

            # 等待一下
            time.sleep(random.uniform(1, 2))

            # 签到
            if not sign_with_requests(session, EMOT_ID, TODAY_SAY):
                raise RuntimeError("签到失败")

            print("=" * 60)
            print("🎉 所有操作完成！")
            print("=" * 60)
            return 0

        except Exception as e:
            print(f"❌ requests 版本执行失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 如果是 429 错误或重定向问题，尝试使用 Playwright（如果可用）
            should_try_playwright = (
                "429" in str(e) or 
                "Too Many Requests" in str(e) or 
                "redirect" in str(e).lower() or
                "TooManyRedirects" in str(e)
            )
            
            if should_try_playwright and USE_PLAYWRIGHT:
                print("\n⚠️ 检测到速率限制或重定向问题，尝试使用 Playwright 版本...")
            else:
                print("\n⚠️ requests 版本失败")
                if not USE_PLAYWRIGHT:
                    print("提示：可以设置环境变量 USE_PLAYWRIGHT=true 来使用 Playwright 版本")
                return 1

    # 使用 Playwright 版本（如果启用或 requests 失败需要回退）
    if USE_PLAYWRIGHT or should_try_playwright:
        try:
            if not USE_PLAYWRIGHT and not should_try_playwright:
                raise RuntimeError("Playwright 模式未启用")

            print("=" * 60)
            print("🚀 使用 Playwright 版本")
            print("=" * 60)

            with sync_playwright() as p:
                # 启动浏览器
                # 如果 Cloudflare 挑战一直失败，可以尝试 headless=False（显示浏览器窗口）
                # 在某些情况下，非 headless 模式更容易通过 Cloudflare 挑战
                use_headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
                print(f"启动浏览器 (headless={use_headless})...")
                browser = p.chromium.launch(
                    headless=use_headless,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )

                # 创建上下文（模拟真实浏览器，增加更多指纹信息）
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    # 忽略 HTTPS 错误（如果需要）
                    ignore_https_errors=False,
                    # 设置语言和时区
                    locale='zh-CN',
                    timezone_id='Asia/Shanghai',
                    # 设置权限
                    permissions=['geolocation'],
                    # 设置地理位置（可选）
                    geolocation={'latitude': 39.9042, 'longitude': 116.4074},
                    # 设置屏幕信息
                    screen={'width': 1920, 'height': 1080},
                    # 设置颜色方案
                    color_scheme='light',
                    # 设置额外的 HTTP 头
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0',
                    }
                )

                # 设置请求拦截，处理网络错误
                def handle_route(route):
                    try:
                        route.continue_()
                    except:
                        pass

                context.route("**/*", handle_route)

                # 创建页面
                page = context.new_page()

                # 设置默认导航超时（在页面上设置，而不是在 context 上）
                page.set_default_navigation_timeout(60000)
                page.set_default_timeout(60000)

                # 注入 JavaScript 来模拟真实浏览器环境
                page.add_init_script("""
                    // 覆盖 navigator.webdriver
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });

                    // 添加 Chrome 对象
                    window.chrome = {
                        runtime: {}
                    };

                    // 覆盖 plugins
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });

                    // 覆盖 languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['zh-CN', 'zh', 'en']
                    });
                """)

                try:
                    # 登录
                    if not login_with_playwright(page, USERNAME, PASSWORD):
                        raise RuntimeError("登录失败")

                    # 等待一下
                    time.sleep(random.uniform(2, 4))

                    # 签到
                    if not sign_with_playwright(page):
                        raise RuntimeError("签到失败")

                    print("🎉 所有操作完成！")

                finally:
                    browser.close()

        except Exception as e:
            print(f"❌ 执行失败: {e}")
            import traceback
            traceback.print_exc()
            return 1

    return 0


if __name__ == "__main__":
    exit(main())

