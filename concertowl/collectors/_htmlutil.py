"""HTML/JSON 解析公用工具。"""
from __future__ import annotations

import json
import re
from typing import List, Optional

# 匹配 ¥380 / RMB 380 / HK$1,979 / MOP 500 / $1,200 等
_PRICE_RE = re.compile(r"(?:¥|￥|RMB|HK\$|HKD|MOP|MOP\$|US\$|\$)\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
_BARE_NUM_RE = re.compile(r"\b([1-9][0-9]{1,4}(?:\.[0-9]+)?)\b")

SOLD_OUT_KEYS = ["售罄", "已售罄", "缺货", "无票", "售完", "Sold Out", "sold out", "SOLD OUT"]
ON_SALE_KEYS = ["立即购买", "立即预订", "在售", "预订", "购买", "Buy", "Get Tickets", "购票"]


def extract_prices(text: str) -> List[float]:
    out: List[float] = []
    for m in _PRICE_RE.finditer(text or ""):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    return out


def min_price(text: str) -> Optional[float]:
    prices = extract_prices(text)
    return min(prices) if prices else None


def median(values: List[float]) -> Optional[float]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2:
        return vals[mid]
    return round((vals[mid - 1] + vals[mid]) / 2, 2)


def guess_status(text: str) -> str:
    if not text:
        return "未知"
    for k in SOLD_OUT_KEYS:
        if k in text:
            return "售罄"
    for k in ON_SALE_KEYS:
        if k in text:
            return "在售"
    return "未知"


def find_json_block(html: str, var_names: List[str]) -> Optional[dict]:
    """从页面里抠出 window.__XXX__ = {...}; 形式的 JSON。"""
    for var in var_names:
        idx = html.find(var)
        if idx == -1:
            continue
        start = html.find("{", idx)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(html)):
            ch = html[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    blob = html[start : i + 1]
                    try:
                        return json.loads(blob)
                    except Exception:
                        break
    return None
