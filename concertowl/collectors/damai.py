"""大麦官方档位采集器（页面解析，best-effort）。"""
from __future__ import annotations

from typing import List, Optional

from ..models import PriceSnapshot, WatchEvent
from .base import Collector
from . import _htmlutil as H


class DamaiCollector(Collector):
    source = "damai"
    url_hints = ("damai.cn",)

    def _target_url(self, event: WatchEvent) -> Optional[str]:
        return event.official_url or None

    def fetch(self, event: WatchEvent) -> List[PriceSnapshot]:
        url = self._target_url(event)
        if not url:
            return []
        resp = self.get(url)
        if resp is None:
            return []
        html = resp.text

        snaps = self._from_json(event, html)
        if snaps:
            return snaps

        prices = H.extract_prices(html)
        low = min(prices) if prices else None
        if low is None:
            return []
        return [
            self.observation(
                event,
                observed_price=low,
                face_price=low,
                status=H.guess_status(html),
                currency="CNY",
                note="regex-fallback",
            )
        ]

    def _from_json(self, event: WatchEvent, html: str) -> List[PriceSnapshot]:
        data = H.find_json_block(html, ["__INITIAL_STATE__", "__GLOBAL_DATA__", "dataDefault"])
        if not data:
            return []
        tickets = self._dig_tickets(data)
        if not tickets:
            return []
        out: List[PriceSnapshot] = []
        for t in tickets:
            price = _to_float(t.get("price") or t.get("originalPrice") or t.get("current_price"))
            if price is None:
                continue
            name = str(t.get("name") or t.get("priceName") or t.get("skuName") or "")
            status = _status_from(t.get("stockStatus") or t.get("status") or t.get("saleStatus"))
            out.append(
                self.observation(
                    event,
                    observed_price=price,
                    face_price=price,
                    status=status,
                    currency="CNY",
                    note=f"official-tier {name}".strip(),
                )
            )
        return out

    @staticmethod
    def _dig_tickets(data: dict) -> List[dict]:
        found: List[dict] = []

        def walk(node):
            if isinstance(node, dict):
                for key in ("tickets", "skuList", "priceList", "perform", "performBases"):
                    val = node.get(key)
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        found.extend(val)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(data)
        return found


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", ""))
    except ValueError:
        return None
    if f > 100000:
        f = f / 100.0
    return f


def _status_from(v) -> str:
    s = str(v or "").lower()
    if any(k in s for k in ("售罄", "soldout", "sold_out", "缺货", "无票")):
        return "售罄"
    if any(k in s for k in ("在售", "onsale", "on_sale", "可售", "sale")):
        return "在售"
    return "未知"
