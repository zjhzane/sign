#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup

# 登录信息
username = 'zjhzane'  # 输入你的用户名
password = '87890022'  # 输入你的密码

# 创建一个会话对象，保持会话状态
session = requests.Session()

# 登录页面URL
login_url = 'https://bbs.steamtools.net/member.php?mod=logging&action=login'

# 获取登录页面，解析隐藏字段
response = session.get(login_url)
soup = BeautifulSoup(response.text, 'html.parser')

# 获取隐藏的formhash
formhash = soup.find('input', {'name': 'formhash'})['value']

# 提交登录的payload
login_payload = {
    'username': username,
    'password': password,
    'formhash': formhash,
    'referer': 'https://bbs.steamtools.net/',
    'loginsubmit': 'true'
}

# 提交登录请求
login_response = session.post(login_url, data=login_payload)
# 调试使用
# print(login_response.text)



# 检查是否登录成功
if '欢迎您回来' in login_response.text:
    print("登陆成功！")

    # 登录后访问签到页面
    signin_url = 'https://bbs.steamtools.net/plugin.php?id=dc_signin:sign'

    # 获取签到页面以提取 formhash 和其他参数
    signin_page = session.get(signin_url)
    soup = BeautifulSoup(signin_page.text, 'html.parser')

    # 提取 formhash 值
    formhash = soup.find('input', {'name': 'formhash'})['value']

    # 设置你选择的表情ID，例如选择 "开心" 表情
    emotid = 1  # 你可以根据需要选择其他表情 ID，例如 2, 3, 等

    # 设置留言内容，这里我设置为空，你可以自定义
    content = "开心超人"
    # 构造 POST 请求数据
    data = {
        'formhash': formhash,
        'signsubmit': 'yes',
        'handlekey': 'signin',
        'emotid': emotid,
        'content': content,
    }
    signin_response = session.post(signin_url, data=data)
    # 调试使用
    # print(signin_response.text)

    # 检查是否签到成功
    if '签到成功' in signin_response.text:
        print("签到成功！")
    else:
        print("签到失败，请稍后再试。")
else:
    print("登录失败，请检查用户名和密码。")

