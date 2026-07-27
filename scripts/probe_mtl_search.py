"""Probe MoreTickets global public search/list APIs."""
from __future__ import annotations

import json

import requests

BASE = "https://api-global.moretickets.com"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.moretickets.com",
    "Referer": "https://www.moretickets.com/",
}


def call(path, params=None, method="GET", body=None):
    url = BASE + path
    try:
        if method == "GET":
            r = requests.get(url, headers=UA, params=params, timeout=20)
        else:
            r = requests.post(url, headers={**UA, "Content-Type": "application/json"}, params=params, json=body, timeout=20)
        print(f"\n=== {method} {r.status_code} {r.url} ===")
        try:
            data = r.json()
            print(json.dumps(data, ensure_ascii=False)[:2000])
            return data
        except Exception:
            print(r.text[:500])
            return None
    except Exception as e:
        print("ERR", path, e)
        return None


# Search
for method, body in [
    ("GET", None),
]:
    call("/pub/search/v1/search", params={"keyword": "陈奕迅", "page": 1, "pageSize": 20}, method=method)

call("/pub/search/v1/search", method="POST", body={"keyword": "陈奕迅", "page": 1, "pageSize": 20})
call("/pub/search/v1/search", method="POST", body={"keyword": "Eason Chan", "pageNo": 1, "pageSize": 20})
call("/pub/home/v2/show/list", params={"page": 1, "pageSize": 20})
call("/pub/home/v2/show/list", method="POST", body={"page": 1, "pageSize": 20})
call("/pub/home/v1/show/explore", params={"page": 1})
call("/pub/home/v1/city/list")
call("/pub/search/v1/search/hot_shows")
call("/pub/home/v1/location/list")
