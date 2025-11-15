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
    for p in patterns:
        m = re.search(p, html, re.S)
        if m:
            return m.group(group)
    return None

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
            html = r.text
            
            # 检查是否被 Cloudflare 拦截
            ensure_not_cf(html)
            
            formhash = pick(1, html,
                r'name="formhash"\s+value="([0-9A-Za-z]+)"',
                r"FORMHASH\s*=\s*'([0-9A-Za-z]+)'",
            )
            loginhash = pick(1, html,
                r'loginhash=([A-Za-z0-9]+)',
                r'id="main_messa\w+_([A-Za-z0-9]+)"',
            )
            
            if not (formhash and loginhash):
                print(f"未找到 formhash 或 loginhash，响应片段：\n{html[:400]}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(5, 10))
                    continue
                raise RuntimeError("未找到 formhash 或 loginhash，片段：\n" + html[:400])
            
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
            html = r.text
            ensure_not_cf(html)
            
            time.sleep(random.uniform(1, 2))
            
            m = re.search(r'name="formhash"\s+value="([0-9A-Za-z]+)"', html) or \
                re.search(r"FORMHASH\s*=\s*'([0-9A-Za-z]+)'", html)
            
            if m:
                formhash = m.group(1)
                print(f"✅ 获取到签到 formhash: {formhash[:10]}...")
                return formhash
            
            if attempt < max_retries - 1:
                print(f"未找到签到 formhash，等待后重试...")
                time.sleep(random.uniform(3, 5))
                continue
                
            raise RuntimeError("未找到签到 formhash（可能未登录）\n" + html[:400])
            
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

