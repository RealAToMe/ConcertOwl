"""Find show-by-id style endpoints in SPA."""
from __future__ import annotations

import re
import requests

js = requests.get(
    "https://www.moretickets.com/assets/index-Cr2VfMj1.js",
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30,
).text

paths = sorted(set(re.findall(r"/pub/[a-zA-Z0-9_./\-]+", js)))
for p in paths:
    if any(k in p.lower() for k in ("show", "search", "tour", "home", "invent", "session", "detail")):
        print(p)
