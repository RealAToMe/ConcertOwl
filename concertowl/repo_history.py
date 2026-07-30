"""Git-friendly repository history storage.

Price observations are written as immutable JSONL files, one file per
collection run.  A compact latest-state index supports change-only recording
plus one heartbeat per local calendar day.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, Mapping, Optional

from .models import PriceSnapshot

LATEST_VERSION = 1


def data_root_from_env() -> Path:
    value = os.environ.get("CONCERTOWL_DATA_DIR", "").strip()
    return Path(value) if value else Path("data")


def current_run_id() -> str:
    value = os.environ.get("CONCERTOWL_RUN_ID") or os.environ.get("GITHUB_RUN_ID")
    if value:
        return _safe_component(value)
    return datetime.now().strftime("local-%Y%m%dT%H%M%S")


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip(".-")
    return cleaned or "unknown"


def _json_dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _canonical_note(note: str) -> str:
    return " ".join((note or "").split())


def observation_series_key(payload: Mapping[str, object]) -> str:
    """Return a stable identity for one event/source/tier series."""
    identity = {
        "event_id": payload.get("event_id") or "",
        "source": payload.get("source") or "",
        "show_datetime": payload.get("show_datetime") or "",
        "face_price": payload.get("face_price"),
        "note": _canonical_note(str(payload.get("note") or "")),
    }
    raw = json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def observation_fingerprint(payload: Mapping[str, object]) -> str:
    """Hash only market values; derived day counters do not create changes."""
    market = {
        "observed_price": payload.get("observed_price"),
        "status": payload.get("status") or "",
        "currency": payload.get("currency") or "",
    }
    raw = json.dumps(market, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def iter_observations(data_root: Path | str) -> Iterator[dict]:
    root = Path(data_root)
    prices = root / "prices"
    if not prices.exists():
        return
    for path in sorted(prices.glob("*/*/*/*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


def iter_run_manifests(data_root: Path | str) -> Iterator[dict]:
    root = Path(data_root)
    runs = root / "runs"
    if not runs.exists():
        return
    for path in sorted(runs.glob("*/*/*/*.json")):
        with path.open("r", encoding="utf-8") as handle:
            yield json.load(handle)


class RepoHistory:
    """Buffer and atomically finalize one repository-backed collection run."""

    def __init__(
        self,
        data_root: Path | str,
        *,
        run_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ):
        self.root = Path(data_root)
        self.run_id = _safe_component(run_id or current_run_id())
        self.now = now or datetime.now()
        self.started_at = self.now.isoformat(timespec="seconds")
        self.latest_path = self.root / "meta" / "latest.json"
        self.latest = self._load_latest()
        self.records: list[dict] = []
        self.seen = 0
        self.changed = 0
        self.heartbeats = 0
        self.unchanged = 0

    @property
    def date_path(self) -> Path:
        return Path(
            f"{self.now.year:04d}",
            f"{self.now.month:02d}",
            f"{self.now.day:02d}",
        )

    @property
    def observations_path(self) -> Path:
        return self.root / "prices" / self.date_path / f"{self.run_id}.jsonl"

    @property
    def manifest_path(self) -> Path:
        return self.root / "runs" / self.date_path / f"{self.run_id}.json"

    def _load_latest(self) -> Dict[str, dict]:
        if not self.latest_path.exists():
            return {}
        try:
            payload = json.loads(self.latest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if isinstance(payload, dict) and "series" in payload:
            series = payload.get("series")
            return series if isinstance(series, dict) else {}
        return payload if isinstance(payload, dict) else {}

    def record(self, snapshots: Iterable[PriceSnapshot]) -> int:
        """Buffer changed observations or today's first unchanged heartbeat."""
        accepted = 0
        today = self.now.date().isoformat()
        for snap in snapshots:
            if not snap.artist:
                continue
            if snap.observed_price is None and "face_only" not in (snap.note or ""):
                continue
            if snap.observed_price is not None and snap.observed_price <= 0:
                continue
            self.seen += 1
            payload = asdict(snap)
            key = observation_series_key(payload)
            fingerprint = observation_fingerprint(payload)
            previous = self.latest.get(key)

            if previous is None:
                kind = "initial"
            elif previous.get("fingerprint") != fingerprint:
                kind = "change"
            elif previous.get("heartbeat_date") != today:
                kind = "heartbeat"
            else:
                self.unchanged += 1
                continue

            record = dict(payload)
            record.update(
                {
                    "series_key": key,
                    "collect_run_id": self.run_id,
                    "record_kind": kind,
                }
            )
            self.records.append(record)
            accepted += 1
            if kind == "heartbeat":
                self.heartbeats += 1
            else:
                self.changed += 1
            self.latest[key] = {
                "fingerprint": fingerprint,
                "observed_at": snap.observed_at,
                "heartbeat_date": today,
                "event_id": snap.event_id,
                "artist": snap.artist,
                "source": snap.source,
                "face_price": snap.face_price,
            }
        return accepted

    def finalize(self, manifest: Optional[Mapping[str, object]] = None) -> dict:
        """Write immutable observations, manifest, and latest index once."""
        if self.manifest_path.exists():
            existing = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            existing["idempotent_replay"] = True
            return existing

        persisted_records = self.records
        if self.observations_path.exists():
            persisted_records = []
            with self.observations_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        persisted_records.append(json.loads(line))
        elif self.records:
            self.observations_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.observations_path.with_suffix(".jsonl.tmp")
            with temp_path.open("w", encoding="utf-8", newline="\n") as out:
                for record in self.records:
                    out.write(
                        json.dumps(
                            record,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
            os.replace(temp_path, self.observations_path)

        latest_payload = {
            "version": LATEST_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "series": self.latest,
        }
        _json_dump(self.latest_path, latest_payload)

        result = dict(manifest or {})
        result.update(
            {
                "run_id": self.run_id,
                "started_at": self.started_at,
                "completed_at": datetime.now().isoformat(timespec="seconds"),
                "status": result.get("status") or "success",
                "records_seen": self.seen,
                "records_written": len(persisted_records),
                "changes": sum(
                    row.get("record_kind") in ("initial", "change")
                    for row in persisted_records
                ),
                "heartbeats": sum(
                    row.get("record_kind") == "heartbeat"
                    for row in persisted_records
                ),
                "unchanged": self.unchanged,
                "observation_file": (
                    self.observations_path.relative_to(self.root).as_posix()
                    if persisted_records
                    else ""
                ),
            }
        )
        _json_dump(self.manifest_path, result)
        return result


def rebuild_latest(data_root: Path | str) -> dict:
    """Rebuild latest.json from all observation files."""
    root = Path(data_root)
    latest: Dict[str, dict] = {}
    for record in iter_observations(root):
        key = record.get("series_key") or observation_series_key(record)
        at = str(record.get("observed_at") or "")
        previous = latest.get(key)
        if previous and str(previous.get("observed_at") or "") > at:
            continue
        latest[key] = {
            "fingerprint": observation_fingerprint(record),
            "observed_at": at,
            "heartbeat_date": at[:10],
            "event_id": record.get("event_id") or "",
            "artist": record.get("artist") or "",
            "source": record.get("source") or "",
            "face_price": record.get("face_price"),
        }
    _json_dump(
        root / "meta" / "latest.json",
        {
            "version": LATEST_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "series": latest,
        },
    )
    return latest
