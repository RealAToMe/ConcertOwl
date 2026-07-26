"""摩天轮 / MoreTickets 二手挂牌最低价采集器。

优先走国际站公开 API（api-global.moretickets.com）按 showId 刷新最低挂牌价；
若没有 showId，再回退到页面解析。

挂牌价 ≠ 成交价，只作观察指标。
"""
from __future__ import annotations

from typing import List, Optional

from ..config import match_artist
from ..models import PriceSnapshot, WatchEvent
from ..mtl_api import MoreTicketsClient, parse_show_id_from_url
from .base import Collector
from . import _htmlutil as H


class MoreTicketsCollector(Collector):
    source = "moretickets"
    url_hints = ("moretickets.com", "motianlun", "piaofutong", "mtl_")

    def __init__(self, min_interval: float = 1.2, timeout: float = 15.0):
        super().__init__(min_interval=min_interval, timeout=timeout)
        self._api = MoreTicketsClient(min_interval=min_interval, timeout=timeout)

    def handles(self, event: WatchEvent) -> bool:
        if event.event_id.startswith("mtl_"):
            return True
        return super().handles(event)

    def _target_url(self, event: WatchEvent) -> Optional[str]:
        return event.secondary_url or None

    def _show_id(self, event: WatchEvent) -> Optional[str]:
        if event.event_id.startswith("mtl_"):
            return event.event_id[4:]
        return parse_show_id_from_url(event.secondary_url or "")

    def fetch(self, event: WatchEvent) -> List[PriceSnapshot]:
        show_id = self._show_id(event)
        if show_id:
            snap = self._from_api(event, show_id)
            if snap:
                return [snap]

        url = self._target_url(event)
        if not url:
            return [self._error_snapshot(event, "no showId/url")]
        return self._from_html(event, url)

    def _from_api(self, event: WatchEvent, show_id: str) -> Optional[PriceSnapshot]:
        art = match_artist(event.artist)
        keywords = []
        if art:
            keywords = [art.name] + list(art.aliases)
        keywords.append(event.artist)
        keywords = [k for k in keywords if k]

        hit_price = None
        currency = ""
        status = "未知"
        for kw in keywords[:4]:
            for show in self._api.search(kw):
                if show.show_id != show_id:
                    continue
                hit_price = show.min_price
                currency = show.currency
                status = {
                    "ONSALE": "在售",
                    "SOLDOUT": "售罄",
                    "PENDING": "预售/待开售",
                }.get((show.status or "").upper(), show.status or "未知")
                break
            if hit_price is not None:
                break

        if hit_price is None and not currency:
            # 仍写一条，便于知道采过但暂无报价
            return self._base_snapshot(
                event,
                tier="overall_min",
                face_price=None,
                listed_min=None,
                official_status=status,
                raw_note=f"api no-price showId={show_id}",
            )

        return self._base_snapshot(
            event,
            tier="overall_min",
            face_price=None,
            listed_min=hit_price,
            premium_ratio=self._premium_ratio(event, hit_price),
            official_status=status,
            raw_note=f"api {currency} showId={show_id}".strip(),
        )

    def _from_html(self, event: WatchEvent, url: str) -> List[PriceSnapshot]:
        resp = self.get(url)
        if resp is None:
            return [self._error_snapshot(event, "fetch failed / blocked")]
        html = resp.text

        snaps = self._from_embedded_json(event, html)
        if snaps:
            return snaps

        prices = H.extract_prices(html)
        low = min(prices) if prices else None
        status = H.guess_status(html)
        return [
            self._base_snapshot(
                event,
                tier="overall_min",
                face_price=None,
                listed_min=low,
                listed_median=H.median(prices),
                premium_ratio=self._premium_ratio(event, low),
                official_status=status,
                raw_note=f"listings~{len(prices)}" if low else "no-price-parsed",
            )
        ]

    def _from_embedded_json(self, event: WatchEvent, html: str) -> List[PriceSnapshot]:
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
                tier="overall_min",
                face_price=None,
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
            for key in ("price", "minPrice", "sellPrice", "ticketPrice", "salePrice", "minSalePrice"):
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
