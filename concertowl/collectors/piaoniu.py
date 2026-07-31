"""票牛公开网页 API：按场次、票面档位采集最低挂牌价。"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..models import PriceSnapshot, WatchEvent
from .base import Collector

API_ORIGIN = "https://x.piaoniu.com"


def parse_activity_id(url: str) -> Optional[str]:
    match = re.search(r"/activity/(\d+)", url or "")
    return match.group(1) if match else None


def _timestamp_iso(value) -> str:
    try:
        dt = datetime.fromtimestamp(
            float(value) / 1000,
            tz=timezone(timedelta(hours=8)),
        )
        return dt.replace(tzinfo=None).isoformat(timespec="minutes")
    except (TypeError, ValueError, OSError):
        return ""


class PiaoniuCollector(Collector):
    source = "piaoniu"
    url_hints = ("piaoniu.com",)

    def __init__(self, min_interval: float = 1.2, timeout: float = 15.0):
        super().__init__(min_interval=min_interval, timeout=timeout)
        self._activity_cache: dict[str, dict | None] = {}
        self._categories_cache: dict[str, list | None] = {}
        self._session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{API_ORIGIN}/",
            }
        )

    def handles(self, event: WatchEvent) -> bool:
        return bool(self._activity_id(event))

    def _target_url(self, event: WatchEvent) -> Optional[str]:
        return event.piaoniu_url or event.secondary_url or None

    def _activity_id(self, event: WatchEvent) -> Optional[str]:
        return parse_activity_id(event.piaoniu_url or "") or parse_activity_id(
            event.secondary_url or ""
        )

    def _json(self, path: str, **kwargs):
        resp = self.get(API_ORIGIN + path, **kwargs)
        if resp is None:
            return None
        resp.encoding = "utf-8"
        try:
            return resp.json()
        except ValueError:
            return None

    def _activity(self, activity_id: str) -> dict | None:
        if activity_id not in self._activity_cache:
            payload = self._json(f"/api/v1/activities/{activity_id}.json")
            self._activity_cache[activity_id] = (
                payload if isinstance(payload, dict) else None
            )
        return self._activity_cache[activity_id]

    def _categories(self, event_id: str) -> list | None:
        if event_id not in self._categories_cache:
            payload = self._json(
                "/api/v1/ticketCategories.json",
                params={"b2c": "true", "eventId": event_id},
            )
            self._categories_cache[event_id] = (
                payload if isinstance(payload, list) else None
            )
        return self._categories_cache[event_id]

    @staticmethod
    def _matching_sessions(event: WatchEvent, sessions: list) -> list:
        """Select only the Piaoniu session represented by this Watchlist event."""
        valid = [session for session in sessions if session.get("id")]
        target_date = (event.show_datetime or "")[:10]
        if target_date:
            return [
                session
                for session in valid
                if _timestamp_iso(
                    session.get("start") or session.get("defaultStart")
                )[:10]
                == target_date
            ]
        # A manually linked single-session activity is unambiguous even if the
        # Watchlist row has no date. Multi-session activities must not be merged.
        return valid if len(valid) == 1 else []

    def fetch(self, event: WatchEvent) -> List[PriceSnapshot]:
        activity_id = self._activity_id(event)
        if not activity_id:
            return []
        activity = self._activity(activity_id)
        if activity is None:
            return []

        out: List[PriceSnapshot] = []
        sessions = self._matching_sessions(event, activity.get("events") or [])
        for session in sessions:
            event_id = str(session["id"])
            categories = self._categories(event_id)
            if categories is None:
                continue
            session_event = replace(
                event,
                show_datetime=_timestamp_iso(
                    session.get("start") or session.get("defaultStart")
                )
                or event.show_datetime,
            )
            session_name = str(session.get("specification") or "")
            for category in categories:
                observed = category.get("lowPrice")
                face = category.get("originPrice")
                has_ticket = bool(category.get("hasTicket"))
                status = "在售" if has_ticket else "售罄"
                face_only = observed in (None, "")
                out.append(
                    self.observation(
                        session_event,
                        observed_price=(
                            None if face_only else float(observed)
                        ),
                        face_price=float(face) if face not in (None, "") else None,
                        status=status,
                        currency="CNY",
                        note=(
                            f"activity={activity_id} session={event_id} "
                            f"{session_name} tier={category.get('specification') or ''}"
                            f"{' face_only' if face_only else ''}"
                        ).strip(),
                    )
                )
        return out
