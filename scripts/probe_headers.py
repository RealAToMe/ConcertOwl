"""Find auth/header requirements around inventory POST in SPA."""
from __future__ import annotations

import re
import requests

js = requests.get(
    "https://www.moretickets.com/assets/index-Cr2VfMj1.js",
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30,
).text

for needle in ["inventory_list", "F.post", "headers", "language", "currency", "X-", "authorization", "seatPlan", "facePrice", "originalPrice", "ticketPlans"]:
    idxs = [m.start() for m in re.finditer(re.escape(needle), js, flags=re.I)]
    print(needle, len(idxs))

# Extract axios/fetch interceptor header setup near 'api-global'
for m in re.finditer(r".{0,80}api-global\.moretickets\.com.{0,200}", js):
    print("CTX", m.group(0)[:260])
    break

# Find header key assignments
for pat in [
    r"language[^,]{0,40}",
    r"Currency[^,]{0,40}",
    r"currencyCode[^,]{0,40}",
    r"x-[a-z-]+",
    r"Authorization[^,]{0,60}",
]:
    hits = sorted(set(re.findall(pat, js, flags=re.I)))[:20]
    print(pat, hits)
