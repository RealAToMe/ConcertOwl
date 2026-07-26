"""摩天轮 / MoreTickets 二手挂牌最低价采集器。

覆盖：
- 大陆：m.moretickets.com / motianlun.cn
- 港澳：moretickets.com 国际站（HK$ 挂牌）

摩天轮不提供个人公开 API；用页面解析拿「档位最低挂牌价」。
挂牌价 ≠ 成交价，只作代理指标。
"""
from __future__ import annotations

from typing import List, Optional

from ..models import PriceSnapshot, WatchEvent
from .base import Collector
from . import _htmlutil as H


class MoreTicketsCollector(Collector):
    source = "moretickets"
    url_hints = ("moretickets.com", "motianlun", "piaofutong")

    def _target_url(self, event: WatchEvent) -> Optional[str]:
        return event.secondary_url or None

    def fetch(self, event: WatchEvent) -> List[PriceSnapshot]:
        url = self._target_url(event)
        if not url:
            return []
        resp = self.get(url)
        if resp is None:
            return [self._error_snapshot(event, "fetch failed / blocked")]
        html = resp.text

        # 优先 JSON（详情页常带 __NUXT__ / __INITIAL_STATE__）
        snaps = self._from_json(event, html)
        if snaps:
            return snaps

        prices = H.extract_prices(html)
        low = min(prices) if prices else None
        status = H.guess_status(html)
        return [
            self._base_snapshot(
                event,
                tier="最低挂牌",
                listed_min=low,
                listed_median=H.median(prices),
                premium_ratio=self._premium_ratio(event, low),
                official_status=status,
                raw_note=f"listings~{len(prices)}" if low else "no-price-parsed",
            )
        ]

    def _from_json(self, event: WatchEvent, html: str) -> List[PriceSnapshot]:
        data = H.find_json_block(html, ["__NUXT__", "__INITIAL_STATE__"])
        if not data:
            return []
        prices: List[float] = []
        self._collect_prices(data, prices)
        if not prices:
            return []
        low = min(prices)
        return [
            self._base_snapshot(
                event,
                tier="最低挂牌",
                listed_min=low,
                listed_median=H.median(prices),
                premium_ratio=self._premium_ratio(event, low),
                official_status="在售",
                raw_note=f"json listings~{len(prices)}",
            )
        ]

    @staticmethod
    def _collect_prices(node, out: List[float]) -> None:
        if isinstance(node, dict):
            for key in ("price", "minPrice", "sellPrice", "ticketPrice", "salePrice"):
                v = node.get(key)
                try:
                    if v is not None:
                        f = float(str(v).replace(",", ""))
                        if 10 <= f <= 100000:
                            out.append(f)
                except (ValueError, TypeError):
                    pass
            for v in node.values():
                MoreTicketsCollector._collect_prices(v, out)
        elif isinstance(node, list):
            for v in node:
                MoreTicketsCollector._collect_prices(v, out)
