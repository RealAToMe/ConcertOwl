"""大麦（damai.cn）官方价 / 售罄状态采集器。

大麦无公开个人 API，这里走详情页解析：
1. 优先从页面 window.__INITIAL_STATE__ / __GLOBAL_DATA__ 抠 JSON 里的票档价格；
2. 失败则回退到正则抓价格区间与售罄关键词。

大麦反爬较强（IP 限制 / Cookie / 验证码）。个人低频使用；坏了按需维护。
"""
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
            return [self._error_snapshot(event, "fetch failed / blocked")]
        html = resp.text

        snaps = self._from_json(event, html)
        if snaps:
            return snaps

        # 回退：正则
        status = H.guess_status(html)
        prices = H.extract_prices(html)
        low = min(prices) if prices else None
        return [
            self._base_snapshot(
                event,
                tier="ALL",
                listed_min=low,
                listed_median=H.median(prices),
                premium_ratio=self._premium_ratio(event, low),
                official_status=status,
                raw_note="regex-fallback" if low else "no-price-parsed",
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
            name = str(t.get("name") or t.get("priceName") or t.get("skuName") or "档位")
            status = _status_from(t.get("stockStatus") or t.get("status") or t.get("saleStatus"))
            out.append(
                self._base_snapshot(
                    event,
                    tier=name,
                    listed_min=price,
                    premium_ratio=self._premium_ratio(event, price),
                    official_status=status,
                    raw_note="json",
                )
            )
        return out

    @staticmethod
    def _dig_tickets(data: dict) -> List[dict]:
        """尽力在嵌套 JSON 里找票档数组。"""
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
    # 大麦有时用分为单位
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
