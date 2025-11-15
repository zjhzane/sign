# -*- coding: utf-8 -*-

import re, sys, requests
from bs4 import BeautifulSoup
import os
import cloudscraper
import time
import random

USERNAME = os.getenv("DC_USER")   # 从环境变量取
PASSWORD = os.getenv("DC_PASS")

if not USERNAME or not PASSWORD:
    raise RuntimeError("账号或密码未配置，请在 GitHub Secrets 里设置 DC_USER / DC_PASS")

print("准备登录账号:", USERNAME)

BASE = "https://bbs.steamtools.net"
COOKIE_STR = ""  # 执行登录后，不需要手动填 Cookie；会由 Session 自动管理
EMOT_ID = "1"
TODAY_SAY = ""

def pick(group, html, *patterns):
    """使用正则表达式提取值"""
    for p in patterns:
        m = re.search(p, html, re.S)
        if m:
            return m.group(group)
    return None

def extract_formhash_and_loginhash(html, response=None):
    """使用多种方法提取 formhash 和 loginhash"""
    formhash = None
    loginhash = None
    
    # 确保编码正确
    if response:
        # 尝试自动检测编码
        if response.encoding is None or response.encoding.lower() in ['iso-8859-1', 'windows-1252']:
            response.encoding = response.apparent_encoding or 'utf-8'
        html = response.text
    
    # 方法1: 使用 BeautifulSoup 提取 formhash
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 查找 formhash input
        formhash_input = soup.find('input', {'name': 'formhash'})
        if formhash_input and formhash_input.get('value'):
            formhash = formhash_input.get('value')
            print(f"✅ 通过 BeautifulSoup 找到 formhash: {formhash[:10]}...")
        
        # 查找所有可能的 loginhash 位置
        # 方法1: 从 URL 参数中提取
        login_links = soup.find_all('a', href=re.compile(r'loginhash=([A-Za-z0-9]+)'))
        if login_links:
            m = re.search(r'loginhash=([A-Za-z0-9]+)', login_links[0].get('href', ''))
            if m:
                loginhash = m.group(1)
                print(f"✅ 通过 BeautifulSoup 找到 loginhash (从链接): {loginhash[:10]}...")
        
        # 方法2: 从元素 ID 中提取
        if not loginhash:
            for elem in soup.find_all(id=re.compile(r'main_messa\w+_([A-Za-z0-9]+)')):
                elem_id = elem.get('id', '')
                m = re.search(r'main_messa\w+_([A-Za-z0-9]+)', elem_id)
                if m:
                    loginhash = m.group(1)
                    print(f"✅ 通过 BeautifulSoup 找到 loginhash (从ID): {loginhash[:10]}...")
                    break
        
        # 方法3: 从 JavaScript 变量中提取
        if not loginhash:
            scripts = soup.find_all('script')
            for script in scripts:
                script_text = script.string or ''
                m = re.search(r'loginhash\s*[=:]\s*["\']([A-Za-z0-9]+)["\']', script_text)
                if m:
                    loginhash = m.group(1)
                    print(f"✅ 通过 BeautifulSoup 找到 loginhash (从JS): {loginhash[:10]}...")
                    break
        
        # 方法4: 从 JavaScript 中的 FORMHASH 变量提取（如果 formhash 还没找到）
        if not formhash:
            scripts = soup.find_all('script')
            for script in scripts:
                script_text = script.string or ''
                m = re.search(r'FORMHASH\s*=\s*["\']([0-9A-Za-z]+)["\']', script_text, re.IGNORECASE)
                if m:
                    formhash = m.group(1)
                    print(f"✅ 通过 BeautifulSoup 找到 formhash (从JS): {formhash[:10]}...")
                    break
                    
    except Exception as e:
        print(f"⚠️ BeautifulSoup 解析出错: {e}")
    
    # 方法2: 使用正则表达式作为回退
    if not formhash:
        formhash = pick(1, html,
            r'name=["\']formhash["\']\s+value=["\']([0-9A-Za-z]+)["\']',
            r'name=["\']formhash["\']\s+value=([0-9A-Za-z]+)',
            r'FORMHASH\s*=\s*["\']([0-9A-Za-z]+)["\']',
            r'formhash["\']?\s*[:=]\s*["\']?([0-9A-Za-z]+)',
        )
        if formhash:
            print(f"✅ 通过正则表达式找到 formhash: {formhash[:10]}...")
    
    if not loginhash:
        loginhash = pick(1, html,
            r'loginhash=([A-Za-z0-9]+)',
            r'loginhash["\']?\s*[:=]\s*["\']?([A-Za-z0-9]+)',
            r'id=["\']main_messa\w+_([A-Za-z0-9]+)["\']',
            r'main_messa\w+_([A-Za-z0-9]+)',
        )
        if loginhash:
            print(f"✅ 通过正则表达式找到 loginhash: {loginhash[:10]}...")
    
    return formhash, loginhash

def ensure_not_cf(html: str):
    low = html.lower()
    if "cloudflare" in low and ("cf-chl" in low or "just a moment" in low):
        raise RuntimeError("被 Cloudflare 挑战拦截，需使用 cloudscraper（已用）或更稳定的运行环境/IP")

def create_session():
    """创建并配置 cloudscraper 会话"""
    # 使用更真实的浏览器配置
    sess = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "mobile": False
        },
        delay=10,  # 增加延迟，模拟真实用户
        debug=False
    )
    
    # 设置更真实的请求头
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    
    return sess

def login(sess, username, password, max_retries=3):
    """登录函数，带重试机制"""
    for attempt in range(max_retries):
        try:
            print(f"尝试登录 (第 {attempt + 1}/{max_retries} 次)...")
            
            # 先访问主页，建立会话
            print("访问主页建立会话...")
            sess.get(BASE, timeout=30)
            time.sleep(random.uniform(2, 4))  # 随机延迟 2-4 秒
            
            # 1) 拿弹窗登录页（inajax），解析 loginhash + formhash
            login_url = f"{BASE}/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1"
            print(f"获取登录页面: {login_url}")
            
            r = sess.get(login_url, timeout=30)
            
            # 确保编码正确
            if r.encoding is None or r.encoding.lower() in ['iso-8859-1', 'windows-1252']:
                r.encoding = r.apparent_encoding or 'utf-8'
            
            html = r.text
            
            # 调试信息：显示响应状态和内容长度
            print(f"响应状态码: {r.status_code}")
            print(f"响应编码: {r.encoding}")
            print(f"响应内容长度: {len(html)} 字符")
            
            # 检查是否被 Cloudflare 拦截
            ensure_not_cf(html)
            
            # 使用改进的提取函数
            formhash, loginhash = extract_formhash_and_loginhash(html, r)
            
            # 如果仍然找不到，输出更多调试信息
            if not formhash or not loginhash:
                print(f"\n⚠️ 未找到 formhash 或 loginhash")
                print(f"formhash: {formhash}")
                print(f"loginhash: {loginhash}")
                print(f"\n响应前 1000 字符:\n{html[:1000]}")
                print(f"\n响应后 500 字符:\n{html[-500:]}")
                
                # 尝试保存 HTML 到文件（在 GitHub Actions 中可能有用）
                try:
                    debug_file = f"login_debug_{attempt + 1}.html"
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(html)
                    print(f"已保存调试 HTML 到: {debug_file}")
                except Exception as e:
                    print(f"无法保存调试文件: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(5, 10))
                    continue
                raise RuntimeError(f"未找到 formhash 或 loginhash\nformhash: {formhash}\nloginhash: {loginhash}\n响应片段：\n{html[:1000]}")
            
            print(f"获取到 formhash: {formhash[:10]}..., loginhash: {loginhash[:10]}...")
            time.sleep(random.uniform(1, 2))  # 模拟用户填写表单的时间
            
            # 2) 提交登录（仍走 inajax）
            url = f"{BASE}/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={loginhash}&inajax=1"
            data = {
                "formhash": formhash,
                "username": username,
                "password": password,
                "questionid": "0",
                "answer": "",
                "loginfield": "username",
                "cookietime": "2592000",
                "referer": BASE,
            }
            
            # 更新请求头用于 POST
            sess.headers.update({
                "Referer": login_url,
                "Origin": BASE,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            })
            
            print("提交登录信息...")
            r2 = sess.post(url, data=data, timeout=30)
            time.sleep(random.uniform(1, 2))
            
            ok = ("欢迎您回来" in r2.text) or ("succeedmessage" in r2.text)
            if ok:
                print("✅ 登录成功！")
                return True
            else:
                print(f"登录失败，响应片段：\n{r2.text[:400]}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(5, 10))
                    continue
                raise RuntimeError("登录失败：\n" + r2.text[:400])
                
        except RuntimeError as e:
            if "Cloudflare" in str(e) and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                print(f"⚠️ 被 Cloudflare 拦截，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"⚠️ 发生错误: {e}，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            raise
    
    raise RuntimeError(f"登录失败，已重试 {max_retries} 次")

def get_sign_formhash(sess, max_retries=3):
    """获取签到 formhash，带重试机制"""
    for attempt in range(max_retries):
        try:
            print(f"获取签到页面 (第 {attempt + 1}/{max_retries} 次)...")
            
            # 恢复正常的请求头
            sess.headers.update({
                "Referer": BASE,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            })
            
            r = sess.get(f"{BASE}/plugin.php?id=dc_signin&mobile=no", timeout=30)
            
            # 确保编码正确
            if r.encoding is None or r.encoding.lower() in ['iso-8859-1', 'windows-1252']:
                r.encoding = r.apparent_encoding or 'utf-8'
            
            html = r.text
            ensure_not_cf(html)
            
            print(f"响应状态码: {r.status_code}")
            print(f"响应编码: {r.encoding}")
            print(f"响应内容长度: {len(html)} 字符")
            
            time.sleep(random.uniform(1, 2))
            
            # 使用 BeautifulSoup 提取 formhash
            formhash = None
            try:
                soup = BeautifulSoup(html, 'html.parser')
                formhash_input = soup.find('input', {'name': 'formhash'})
                if formhash_input and formhash_input.get('value'):
                    formhash = formhash_input.get('value')
                    print(f"✅ 通过 BeautifulSoup 找到签到 formhash: {formhash[:10]}...")
            except Exception as e:
                print(f"⚠️ BeautifulSoup 解析出错: {e}")
            
            # 如果 BeautifulSoup 没找到，使用正则表达式作为回退
            if not formhash:
                m = re.search(r'name=["\']formhash["\']\s+value=["\']([0-9A-Za-z]+)["\']', html) or \
                    re.search(r'name=["\']formhash["\']\s+value=([0-9A-Za-z]+)', html) or \
                    re.search(r"FORMHASH\s*=\s*['\"]([0-9A-Za-z]+)['\"]", html, re.IGNORECASE)
                
                if m:
                    formhash = m.group(1)
                    print(f"✅ 通过正则表达式找到签到 formhash: {formhash[:10]}...")
            
            if formhash:
                return formhash
            
            # 如果还是找不到，输出调试信息
            print(f"\n⚠️ 未找到签到 formhash")
            print(f"响应前 1000 字符:\n{html[:1000]}")
            print(f"响应后 500 字符:\n{html[-500:]}")
            
            # 尝试保存 HTML 到文件
            try:
                debug_file = f"sign_debug_{attempt + 1}.html"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"已保存调试 HTML 到: {debug_file}")
            except Exception as e:
                print(f"无法保存调试文件: {e}")
            
            if attempt < max_retries - 1:
                print(f"未找到签到 formhash，等待后重试...")
                time.sleep(random.uniform(3, 5))
                continue
                
            raise RuntimeError("未找到签到 formhash（可能未登录）\n" + html[:1000])
            
        except RuntimeError as e:
            if "Cloudflare" in str(e) and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                print(f"⚠️ 被 Cloudflare 拦截，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            raise
    
    raise RuntimeError(f"获取签到 formhash 失败，已重试 {max_retries} 次")

def do_sign(sess, max_retries=3):
    """执行签到，带重试机制"""
    for attempt in range(max_retries):
        try:
            print(f"执行签到 (第 {attempt + 1}/{max_retries} 次)...")
            
            tbs = get_sign_formhash(sess)
            time.sleep(random.uniform(1, 2))
            
            payload = {
                "formhash": tbs,
                "signsubmit": "yes",
                "emotid": EMOT_ID,
                "todaysay": TODAY_SAY,   # 避免含 < > ' " () 之类字符以触发 XSS 检查
            }
            
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{BASE}/plugin.php?id=dc_signin",
                "Origin": BASE,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            
            r = sess.post(f"{BASE}/plugin.php?id=dc_signin:sign&inajax=1",
                          data=payload, headers=headers, timeout=30)
            txt = r.text
            
            # 解析 XML/CDATA 提示并判定结果
            m = re.search(r"<!\[CDATA\[(.*?)\]\]>", txt, re.S)
            msg = (m.group(1) if m else txt).replace("\n", "").replace("\r", "").replace(" ", "")
            print("✅ 签到成功或今天已签：", msg)
            return True
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"⚠️ 签到失败: {e}，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            raise
    
    raise RuntimeError(f"签到失败，已重试 {max_retries} 次")

def main():
    try:
        # 创建 cloudscraper 会话
        sess = create_session()
        
        # 登录
        login(sess, USERNAME, PASSWORD)
        
        # 等待一下再签到
        time.sleep(random.uniform(2, 4))
        
        # 签到
        do_sign(sess)
        
        print("🎉 所有操作完成！")
        
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

