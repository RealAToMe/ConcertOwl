"""Probe POST bodies for tour/inventory detail."""
from __future__ import annotations

import json

import requests

BASE = "https://api-global.moretickets.com"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.moretickets.com",
    "Referer": "https://www.moretickets.com/",
}

show_id = "6a0edbfcff9aa00001849204"
tour_id = "6a0edbc44163d70001072dda"
show_code = "chenli-hongkong-2026-concert"


def post(path, body):
    r = requests.post(BASE + path, headers=UA, json=body, timeout=20)
    print(f"\n=== POST {r.status_code} {path} body={body} ===")
    try:
        print(json.dumps(r.json(), ensure_ascii=False)[:2000])
    except Exception:
        print(r.text[:500])


def get(path, params=None):
    r = requests.get(BASE + path, headers=UA, params=params, timeout=20)
    print(f"\n=== GET {r.status_code} {r.url} ===")
    try:
        print(json.dumps(r.json(), ensure_ascii=False)[:2000])
    except Exception:
        print(r.text[:500])


# tour detail
for body in [
    {"tourId": tour_id},
    {"showId": show_id},
    {"tourId": tour_id, "showId": show_id},
    {"showCode": show_code},
]:
    post("/pub/tour/v1/tour_detail", body)
    get("/pub/tour/v1/tour_detail", body)

# sessions
for body in [
    {"tourId": tour_id, "showId": show_id},
    {"showId": show_id},
    {"tourId": tour_id},
]:
    post("/pub/tour/v2/tour_session_list", body)
    post("/pub/tour/v1/tour_session_list", body)

# inventory
for body in [
    {"showId": show_id, "tourId": tour_id},
    {"showId": show_id},
    {"tourId": tour_id},
    {"sessionId": show_id},
]:
    post("/pub/tour/v2/inventory_list", body)

# tour list
post("/pub/tour/v1/tour_list", {"showId": show_id})
get("/pub/tour/v1/tour_list", {"showId": show_id})
