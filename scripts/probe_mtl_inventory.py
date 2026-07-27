"""Probe inventory + location-filtered lists + mainland hosts."""
from __future__ import annotations

import json

import requests

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


def get(base, path, params=None, headers=None):
    url = base + path
    try:
        r = requests.get(url, headers=headers or UA, params=params, timeout=20)
        print(f"\n=== {r.status_code} {r.url} ===")
        try:
            data = r.json()
            print(json.dumps(data, ensure_ascii=False)[:1800])
            return data
        except Exception:
            print(r.text[:400])
    except Exception as e:
        print("ERR", url, e)


BASE = "https://api-global.moretickets.com"

# Search with English artist names
for kw in ["Eason Chan", "JJ Lin", "Stefanie Sun", "Chen Li", "Zhou Shen"]:
    get(BASE, "/pub/search/v1/search", {"keyword": kw, "page": 1, "pageSize": 10})

# Show list filtered by HK / MO location ids
get(BASE, "/pub/home/v2/show/list", {"page": 1, "pageSize": 5, "locationId": "662e61ac5aa19945010236bf"})
get(BASE, "/pub/home/v2/show/list", {"page": 1, "pageSize": 5, "locationCode": "CN-HK"})

# Inventory for Chen Li HK show
show_id = "6a0edbfcff9aa00001849204"
tour_id = "6a0edbc44163d70001072dda"
get(BASE, "/pub/sale/v2/inventory_list", {"showId": show_id, "tourId": tour_id})
get(BASE, "/pub/sale/v1/inventory_list", {"showId": show_id})
get(BASE, "/pub/sale/v2/inventory_list", {"showId": show_id})
get(BASE, "/pub/tour/v1/tour_session_list", {"showId": show_id, "tourId": tour_id})
get(BASE, "/pub/tour/v2/tour_session_list", {"showId": show_id, "tourId": tour_id})

# Mainland hosts
CN_HOSTS = [
    "https://api.moretickets.com",
    "https://m.moretickets.com",
    "https://www.motianlun.cn",
    "https://api.motianlun.cn",
    "https://appapi.motianlun.cn",
]
for h in CN_HOSTS:
    get(h, "/")
    get(h, "/pub/search/v1/search", {"keyword": "陈奕迅", "page": 1, "pageSize": 5})
