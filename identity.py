# -*- coding: utf-8 -*-
"""从访问来源猜对面是谁。只有两档：我（爸爸/家里人）和陌生人。

判断顺序：
1. QQ 消息：uid 等于配置里的主人 QQ 号 → 爸爸（见下面的 _owner_qqs）
2. 页面访问：X-Forwarded-For / X-Real-IP（nginx 反代会带）或直连 IP
   - 127.0.0.1、局域网段 → 爸爸/家人
   - DICE_OWNER_IPS 里写死的公网 IP（支持 1.2.3.* 通配）→ 爸爸
   - 其它一律陌生人
3. 开了 DICE_BEHIND_PROXY=1 时，反代来的 127.0.0.1 不算爸爸妈妈（怕 nginx 不带 XFF 时全员误判）

配置（都不写进仓库）：
  - 环境变量 DICE_OWNER_QQ / DICE_OWNER_IPS / DICE_BEHIND_PROXY
  - 或者同目录的 config_local.py（已在 .gitignore 里）：OWNER_QQ = "123456789", OWNER_IPS = "1.2.3.4"
"""

import ipaddress
import os

ENV_OWNER_IPS = "DICE_OWNER_IPS"
ENV_OWNER_QQ = "DICE_OWNER_QQ"
ENV_BEHIND_PROXY = "DICE_BEHIND_PROXY"

STRANGER = {"who": "stranger", "label": "陌生的酒客"}
OWNER = {"who": "owner", "label": "爸爸"}


def _local_config():
    """读到同目录 config_local.py 就用它（不进仓库的私人配置）"""
    try:
        import config_local as cl
        return cl
    except Exception:
        return None


def _split(raw):
    return [p.strip() for p in str(raw or "").replace("，", ",").split(",") if p.strip()]


def _owner_patterns():
    raw = os.environ.get(ENV_OWNER_IPS, "")
    if not raw:
        cl = _local_config()
        raw = getattr(cl, "OWNER_IPS", "") if cl else ""
    return _split(raw)


def _owner_qqs():
    raw = os.environ.get(ENV_OWNER_QQ, "")
    if not raw:
        cl = _local_config()
        raw = getattr(cl, "OWNER_QQ", "") if cl else ""
    return _split(raw)


def _match(ip, pat):
    if pat.endswith("*"):
        return ip.startswith(pat[:-1])
    return ip == pat


def _ip(ip):
    try:
        return ipaddress.ip_address(ip)
    except ValueError:
        return None


def _behind_proxy():
    return os.environ.get(ENV_BEHIND_PROXY, "").strip() in ("1", "true", "yes")


def is_owner_ip(ip):
    if not ip:
        return False
    if _behind_proxy() and _ip(ip) and _ip(ip).is_loopback:
        return False          # 这是反代自己，不是人
    for pat in _owner_patterns():
        if _match(ip, pat):
            return True
    addr = _ip(ip)
    if addr is None:
        return False
    return addr.is_loopback or addr.is_private


def client_ip(handler):
    """从 request handler 里抠出真实访客 IP"""
    headers = getattr(handler, "headers", None)
    if headers:
        for name in ("X-Forwarded-For", "X-Real-IP"):
            try:
                val = headers.get(name)
            except Exception:
                val = None
            if val:
                return val.split(",")[0].strip()
    try:
        return handler.client_address[0]
    except Exception:
        return ""


def classify(ip="", uid=""):
    if uid and str(uid) in _owner_qqs():
        return dict(OWNER)
    if is_owner_ip(ip):
        return dict(OWNER)
    return dict(STRANGER)
