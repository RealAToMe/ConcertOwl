"""摩天轮 / MoreTickets 挂牌价采集器（优先公开 API）。"""
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
            return [snap] if snap else []

        url = self._target_url(event)
        if not url:
            return []
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
                currency = show.currency or ""
                status = {
                    "ONSALE": "在售",
                    "SOLDOUT": "售罄",
                    "PENDING": "预售/待开售",
                }.get((show.status or "").upper(), show.status or "未知")
                break
            if hit_price is not None:
                break

        if hit_price is None:
            return None

        # API 暂只能拿到全场最低挂牌；有 face_prices 时仍先记 overall，分档后补
        faces = self.face_price_list(event)
        face = min(faces) if len(faces) == 1 else None
        return self.observation(
            event,
            observed_price=hit_price,
            face_price=face,
            status=status,
            currency=currency,
            note=f"overall_min showId={show_id}",
        )

    def _from_html(self, event: WatchEvent, url: str) -> List[PriceSnapshot]:
        resp = self.get(url)
        if resp is None:
            return []
        html = resp.text
        prices = H.extract_prices(html)
        low = min(prices) if prices else None
        if low is None:
            return []
        return [
            self.observation(
                event,
                observed_price=low,
                face_price=None,
                status=H.guess_status(html),
                note=f"html listings~{len(prices)}",
            )
        ]
