"""Probe candidate discovery endpoints (local only)."""
from __future__ import annotations

import json
import re
import sys

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def try_get(url: str, **kwargs):
    try:
        r = requests.get(url, headers=UA, timeout=20, **kwargs)
        print(f"OK {r.status_code} {len(r.text):6d} {url}")
        print(f"   ct={r.headers.get('content-type','')} final={r.url[:100]}")
        return r
    except Exception as e:
        print(f"ERR {type(e).__name__}: {e} :: {url}")
        return None


def main():
    r = try_get("https://www.moretickets.com/")
    if r:
        scripts = re.findall(r'src=["\']([^"\']+)["\']', r.text)
        print("scripts:", scripts[:30])
        apis = re.findall(r"https?://[A-Za-z0-9._/-]*(?:api|tking|motianlun)[A-Za-z0-9._/-]*", r.text, re.I)
        print("api-ish:", apis[:30])
        print("snippet:", r.text[:800].replace("\n", " "))

    candidates = [
        "https://www.moretickets.com/api/search?keyword=%E9%99%88%E5%A5%95%E8%BF%85",
        "https://www.moretickets.com/search/api?keyword=%E9%99%88%E5%A5%95%E8%BF%85",
        "https://m.motianlun.cn/",
        "https://www.tking.cn/",
        "https://appapi.moretickets.com/",
        "https://www.cityline.com.hk/",
        "https://www.cityline.com.hk/Events.html",
    ]
    for u in candidates:
        try_get(u)

    # damai search page for embedded data
    r2 = try_get("https://search.damai.cn/search.htm", params={"keyword": "陈奕迅"})
    if r2:
        print("damai has punish?", "punish" in r2.text or "_____tmd_____" in r2.text)
        print("damai snippet:", r2.text[:400].replace("\n", " "))


if __name__ == "__main__":
    main()
