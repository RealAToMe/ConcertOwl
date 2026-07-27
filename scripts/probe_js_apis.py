"""Extract MoreTickets API call sites from SPA bundle."""
from __future__ import annotations

import re

import requests

UA = {"User-Agent": "Mozilla/5.0"}
js = requests.get("https://www.moretickets.com/assets/index-Cr2VfMj1.js", headers=UA, timeout=30).text
print("js", len(js))

# Find nearby context for inventory / show detail
for needle in [
    "inventory_list",
    "show_detail",
    "showDetail",
    "minSalePrice",
    "tour_session",
    "pub/tour",
    "pub/sale",
]:
    idxs = [m.start() for m in re.finditer(re.escape(needle), js)]
    print(f"\n{needle}: {len(idxs)} hits")
    for i in idxs[:3]:
        print(js[max(0, i - 120) : i + 180].replace("\n", " "))

# Also find baseURL construction
for m in re.finditer(r"api-global\.moretickets\.com[^\"']{0,80}", js):
    print("host ctx", m.group(0))
    break
