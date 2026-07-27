"""Probe api-global.moretickets.com and Damai search HTML."""
from __future__ import annotations

import json
import re

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


def dump(label, r):
    if r is None:
        print(label, "None")
        return
    print(f"\n=== {label} {r.status_code} {r.url} ===")
    text = r.text
    print("len", len(text), "ct", r.headers.get("content-type"))
    try:
        data = r.json()
        print(json.dumps(data, ensure_ascii=False)[:1500])
    except Exception:
        print(text[:800].replace("\n", " "))


def try_get(url, **kwargs):
    try:
        return requests.get(url, headers=UA, timeout=20, **kwargs)
    except Exception as e:
        print("ERR", url, e)
        return None


paths = [
    "https://api-global.moretickets.com/",
    "https://api-global.moretickets.com/api/search?keyword=Eason",
    "https://api-global.moretickets.com/search?keyword=Eason",
    "https://api-global.moretickets.com/v1/search?keyword=Eason",
    "https://api-global.moretickets.com/show/search?keyword=%E9%99%88%E5%A5%95%E8%BF%85",
    "https://api-global.moretickets.com/api/v1/shows?keyword=Eason",
    "https://api-global.moretickets.com/api/shows?city=Hong%20Kong",
    "https://api-global.moretickets.com/api/home",
    "https://api-global.moretickets.com/home",
]

for u in paths:
    dump(u, try_get(u))

# Fetch SPA JS and extract API paths
r = try_get("https://www.moretickets.com/assets/index-Cr2VfMj1.js")
if r:
    print("\nJS len", len(r.text))
    # find api paths
    hits = sorted(set(re.findall(r"api-global\.moretickets\.com[^\s\"'`]*", r.text)))
    print("host hits", hits[:50])
    paths2 = sorted(set(re.findall(r"[\"'`](/[a-zA-Z0-9_./\-?=&%{}]+)[\"'`]", r.text)))
    api_paths = [p for p in paths2 if "search" in p.lower() or "show" in p.lower() or "event" in p.lower() or "list" in p.lower()]
    print("path-ish", api_paths[:80])

# Damai search page links
r2 = try_get("https://search.damai.cn/search.htm", params={"keyword": "陈奕迅"})
if r2:
    links = re.findall(r"https?://[^\"'\s]*damai\.cn[^\"'\s]*", r2.text)
    print("\ndamai links sample", links[:20])
    ids = re.findall(r"item\.htm\?id=(\d+)", r2.text)
    print("item ids", ids[:20])
    titles = re.findall(r'class="[^"]*name[^"]*"[^>]*>([^<]+)<', r2.text)
    print("names", titles[:10])
    # look for items in script
    for key in ["itemlist", "pageData", "resultData", "searchData"]:
        if key.lower() in r2.text.lower():
            print("found key", key)
