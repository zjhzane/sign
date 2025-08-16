import re
import time
import json
import random
import requests

# 1) 把你在已登录贴吧页面抓到的 Cookie 放到这里（至少包含 BDUSS；完整复制更稳）
BDUSS = "XUyR0VUZ0F3bzB-RFE4MTVnTlQxck5lNEF3ZFlubVhzbG9QcXBCTnRNTEZPalJuSVFBQUFBJCQAAAAAAAAAAAEAAABsQICS1ty93MLXcm9ja3kAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMWtDGfFrQxnT"   # ← 替换
STOKEN= "fc3434c096cb65385b1916f9a1136c4cdaa734b1b57a34ed9b09ada4b59a0e61"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

s = requests.Session()
s.headers.update({"User-Agent": UA, "Referer": "https://tieba.baidu.com/"})

# 用 cookies 字典方式，避免手写 Cookie 头的拼接问题
if BDUSS: s.cookies.set("BDUSS", BDUSS, domain=".baidu.com")


def get_tbs():
    r = s.get("https://tieba.baidu.com/dc/common/tbs", timeout=10)
    j = r.json()
    return j

def onekey_sign(tbs):
    data = {"ie": "utf-8", "tbs": tbs}
    r = s.post("https://tieba.baidu.com/tbmall/onekeySignin1", data=data, timeout=15)
    return r.json()

if __name__ == "__main__":
    j = get_tbs()
    print("tbs接口返回：", j)
    if j.get("is_login") != 1:
        print("未登录/COOKIE失效，请重新从 tieba.baidu.com 复制 BDUSS/BDUSS_BFESS/STOKEN。")
        exit(1)
    resp = onekey_sign(j["tbs"])
    print("一键签到返回：", json.dumps(resp, ensure_ascii=False))