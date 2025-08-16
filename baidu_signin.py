# -*- coding: utf-8 -*-
import re, sys, requests
from bs4 import BeautifulSoup
import os

USERNAME = os.getenv("DC_USER")   # 从环境变量取
PASSWORD = os.getenv("DC_PASS")

if not USERNAME or not PASSWORD:
    raise RuntimeError("账号或密码未配置，请在 GitHub Secrets 里设置 DC_USER / DC_PASS")

print("准备登录账号:", USERNAME)

BASE = "https://bbs.steamtools.net"
COOKIE_STR = ""  # 执行登录后，不需要手动填 Cookie；会由 Session 自动管理
EMOT_ID = "1"
TODAY_SAY = ""

def get_formhash_page(s):
    url = f"{BASE}/plugin.php?id=dc_signin&mobile=no"
    r = s.get(url, timeout=20)
    m = re.search(r'name="formhash"\s+value="([0-9A-Za-z]+)"', r.text) or \
        re.search(r"FORMHASH\s*=\s*'([0-9A-Za-z]+)'", r.text)
    if not m:
        print("未找到 formhash（签到页面获取失败，可能未登录）")
        print(r.text[:500])
        sys.exit(1)
    return m.group(1)

def login(s):
    login_page = s.get(f"{BASE}/member.php?mod=logging&action=login", timeout=20).text
    m = re.search(r'name="formhash"\s+value="([0-9A-Za-z]+)"', login_page)
    if not m:
        print("未能解析 login 表单 page formhash，请手工检查页面")
        sys.exit(1)
    formhash = m.group(1)
    print("登录页面 formhash：", formhash)

    payload = {
        "formhash": formhash,
        "username": USERNAME,
        "password": PASSWORD,
        "questionid": 0,
        "answer": "",
        "referer": BASE
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    r = s.post(f"{BASE}/member.php?mod=logging&action=login&loginsubmit=yes&mobile=no",
               data=payload, headers=headers, timeout=20)
    if "欢迎您回来" not in r.text:
        print("登录失败，页面返回：")
        print(r.text[:500])
        sys.exit(1)
    print("登录成功!")

def do_sign(s):
    formhash = get_formhash_page(s)
    print("签到 formhash:", formhash)

    payload = {
        "formhash": formhash,
        "signsubmit": "yes",
        "emotid": EMOT_ID,
        "todaysay": TODAY_SAY,
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE}/plugin.php?id=dc_signin",
        "Origin": BASE,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Mozilla/5.0",
    }
    r = s.post(f"{BASE}/plugin.php?id=dc_signin:sign&inajax=1",
               data=payload, headers=headers, timeout=20)

    print("签到成功!")


def main():
    s = requests.Session()
    login(s)
    do_sign(s)

if __name__ == "__main__":
    main()

