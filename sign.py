# -*- coding: utf-8 -*-
import re, sys, requests
from bs4 import BeautifulSoup
import os
import cloudscraper

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

def login(sess, username, password):
    # 1) 拿弹窗登录页（inajax），解析 loginhash + formhash
    r = sess.get(f"{BASE}/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1", timeout=20)
    html = r.text
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
        raise RuntimeError("未找到 formhash 或 loginhash，片段：\n" + html[:400])

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
    r2 = sess.post(url, data=data, timeout=20)
    ok = ("欢迎您回来" in r2.text) or ("succeedmessage" in r2.text)
    if not ok:
        raise RuntimeError("登录失败：\n" + r2.text[:400])
    return True

def get_sign_formhash(sess):
    r = sess.get(f"{BASE}/plugin.php?id=dc_signin&mobile=no", timeout=20)
    html = r.text
    ensure_not_cf(html)
    m = re.search(r'name="formhash"\s+value="([0-9A-Za-z]+)"', html) or \
        re.search(r"FORMHASH\s*=\s*'([0-9A-Za-z]+)'", html)
    if not m:
        raise RuntimeError("未找到签到 formhash（可能未登录）\n" + html[:400])
    return m.group(1)

def do_sign(sess):
    tbs = get_sign_formhash(sess)
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
        "User-Agent": "Mozilla/5.0",
    }
    r = sess.post(f"{BASE}/plugin.php?id=dc_signin:sign&inajax=1",
                  data=payload, headers=headers, timeout=20)
    txt = r.text
    # 解析 XML/CDATA 提示并判定结果
    m = re.search(r"<!\[CDATA\[(.*?)\]\]>", txt, re.S)
    msg = (m.group(1) if m else txt).replace("\n", "").replace("\r", "").replace(" ", "")
    print("✅ 签到成功或今天已签：", msg)


def main():
    # 只创建一个 cloudscraper 会话（它继承自 requests.Session，能持久化 Cookie）
    sess = cloudscraper.create_scraper(
        browser={"browser":"chrome","platform":"windows","mobile":False}
    )  # CloudScraper is a requests.Session subclass
    sess.headers.update({"User-Agent":"Mozilla/5.0", "Referer": BASE})

    login(sess, USERNAME, PASSWORD)
    do_sign(sess)

if __name__ == "__main__":
    main()



