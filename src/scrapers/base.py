"""
Base HTTP Fetcher, Raw Data Cache, and Cryptographic Provenance Logger.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ProvenanceRecord:
    """Tracks provenance, timestamps, and cryptographic checksum of an ingested source."""

    source_id: str
    source_name: str
    observation_level: str
    source_url: str
    doi_or_registry: str
    local_raw_path: str
    sha256: str
    byte_size: int
    ingested_at_utc: str
    data_generated_period: str
    record_count: int = 0
    description: str = ""


class BaseScraper:
    """Base scraper with retry, raw caching, and provenance logging."""

    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.provenance_records: List[ProvenanceRecord] = []

    def fetch_bytes(
        self,
        url: str,
        cache_filename: str,
        source_id: str,
        source_name: str,
        observation_level: str,
        doi_or_registry: str,
        data_generated_period: str,
        description: str = "",
        force_refresh: bool = False,
        timeout: int = 45,
        max_retries: int = 3,
    ) -> tuple[bytes, ProvenanceRecord]:
        """Fetch raw bytes from URL (or local raw cache) and record provenance."""
        cache_path = self.raw_dir / cache_filename
        ingested_ts = utc_now_iso()

        if cache_path.exists() and not force_refresh and cache_path.stat().st_size > 0:
            raw_bytes = cache_path.read_bytes()
        else:
            last_err: Optional[Exception] = None
            raw_bytes = b""
            for attempt in range(1, max_retries + 1):
                try:
                    req = urllib.request.Request(
                        url,
                        headers={
                            "User-Agent": "curl/8.5.0",
                            "Accept": "application/json, text/csv, text/plain, */*",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        raw_bytes = resp.read()
                    cache_path.write_bytes(raw_bytes)
                    break
                except Exception as exc:
                    last_err = exc
                    if attempt < max_retries:
                        time.sleep(1.5 * attempt)
            else:
                raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_err}")

        digest = hashlib.sha256(raw_bytes).hexdigest()
        rec = ProvenanceRecord(
            source_id=source_id,
            source_name=source_name,
            observation_level=observation_level,
            source_url=url,
            doi_or_registry=doi_or_registry,
            local_raw_path=str(cache_path),
            sha256=digest,
            byte_size=len(raw_bytes),
            ingested_at_utc=ingested_ts,
            data_generated_period=data_generated_period,
            description=description,
        )
        self.provenance_records.append(rec)
        return raw_bytes, rec

    def fetch_json(
        self,
        url: str,
        cache_filename: str,
        source_id: str,
        source_name: str,
        observation_level: str,
        doi_or_registry: str,
        data_generated_period: str,
        description: str = "",
        force_refresh: bool = False,
    ) -> tuple[Any, ProvenanceRecord]:
        raw_bytes, rec = self.fetch_bytes(
            url=url,
            cache_filename=cache_filename,
            source_id=source_id,
            source_name=source_name,
            observation_level=observation_level,
            doi_or_registry=doi_or_registry,
            data_generated_period=data_generated_period,
            description=description,
            force_refresh=force_refresh,
        )
        return json.loads(raw_bytes.decode("utf-8", errors="replace")), rec
