"""Probe unify.moretickets.com (likely mainland) and header variants."""
from __future__ import annotations

import json
import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.motianlun.cn",
    "Referer": "https://www.motianlun.cn/",
    "Language": "zh_CN",
    "Currency": "CNY",
}


def try_host(base):
    print("\n====", base)
    for path, params in [
        ("/pub/search/v1/search", {"keyword": "陈奕迅", "page": 1, "pageSize": 5}),
        ("/pub/home/v2/show/list", {"page": 1, "pageSize": 5}),
        ("/pub/home/v1/city/list", None),
        ("/pub/home/v1/location/list", None),
    ]:
        try:
            r = requests.get(base + path, headers=UA, params=params, timeout=20)
            print(path, r.status_code, r.text[:400].replace("\n", " "))
        except Exception as e:
            print(path, "ERR", e)


for host in [
    "https://unify.moretickets.com",
    "https://unify-prod.moretickets.com",
    "https://api-global.moretickets.com",
]:
    try_host(host)

# Retry inventory on global with Language/Currency headers
show_id = "6a603a0be8d66b000193a6a3"
tour_id = "6a60386d961ac50001749658"
headers = {
    **UA,
    "Origin": "https://www.moretickets.com",
    "Referer": "https://www.moretickets.com/",
    "Language": "zh_HK",
    "Currency": "HKD",
    "Content-Type": "application/json",
}
for body in [
    {"showId": show_id, "tourId": tour_id},
    {"showId": show_id, "tourId": tour_id, "currencyCode": "HKD"},
]:
    r = requests.post(
        "https://api-global.moretickets.com/pub/tour/v2/inventory_list",
        headers=headers,
        json=body,
        timeout=20,
    )
    print("inv", r.status_code, r.text[:500])

r = requests.post(
    "https://api-global.moretickets.com/pub/tour/v2/tour_session_list",
    headers=headers,
    json={"showId": show_id, "tourId": tour_id},
    timeout=20,
)
print("sess", r.status_code, r.text[:800])
