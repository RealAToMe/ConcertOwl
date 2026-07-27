"""Probe inventory with sessions for a live HK show that has prices."""
from __future__ import annotations

import json
import requests

BASE = "https://api-global.moretickets.com"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.moretickets.com",
    "Referer": "https://www.moretickets.com/",
}

# Silence Wang HK - known from discovery
show_id = "6a603a0be8d66b000193a6a3"
tour_id = "6a60386d961ac50001749658"


def get(path, params=None):
    r = requests.get(BASE + path, headers=UA, params=params, timeout=20)
    print(f"\nGET {r.status_code} {path}")
    print(json.dumps(r.json(), ensure_ascii=False)[:2500])
    return r.json()


def post(path, body):
    r = requests.post(BASE + path, headers=UA, json=body, timeout=20)
    print(f"\nPOST {r.status_code} {path} {body}")
    print(json.dumps(r.json(), ensure_ascii=False)[:2500])
    return r.json()


# sessions
for body in [
    {"showId": show_id, "tourId": tour_id},
    {"showId": show_id},
    {"tourId": tour_id},
]:
    post("/pub/tour/v2/tour_session_list", body)
    post("/pub/tour/v1/tour_session_list", body)

# show session count
get("/pub/tour/v1/show_session_count", {"showId": show_id})
get("/pub/tour/v1/show_session_count", {"tourId": tour_id, "showId": show_id})

# venue zones
post("/pub/tour/v1/venue_zones_detail_list", {"showId": show_id, "tourId": tour_id})
post("/pub/tour/v2/all_zone_list", {"showId": show_id, "tourId": tour_id})
post("/pub/tour/v2/sale_count_list", {"showId": show_id, "tourId": tour_id})

# inventory with extra fields often used
for body in [
    {"showId": show_id, "tourId": tour_id, "pageNo": 1, "pageSize": 50},
    {"showId": show_id, "sessionId": "", "page": 1},
    {"bizShowId": show_id},
    {"showSessionId": show_id},
]:
    post("/pub/tour/v2/inventory_list", body)
