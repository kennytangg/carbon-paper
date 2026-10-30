"""
Append-only, hash-chained commit-reveal ledger that enforces the blind protocol.

The right grid (field ground truth) is sealed at ingestion: only its SHA-256 digest
is committed. The left grid (satellite-only) must commit the digest of its
predictions BEFORE the right grid may be revealed. Every entry carries the hash of
the previous entry, so reordering or editing any entry breaks the chain.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _entry_hash(entry: Dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class BlindLedger:
    GENESIS = "0" * 64

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def entries(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append(self, kind: str, **payload: Any) -> Dict[str, Any]:
        chain = self.entries()
        entry = {
            "seq": len(chain),
            "kind": kind,
            "at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "prev_hash": chain[-1]["entry_hash"] if chain else self.GENESIS,
            **payload,
        }
        entry["entry_hash"] = _entry_hash(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self) -> bool:
        prev = self.GENESIS
        for e in self.entries():
            if e["prev_hash"] != prev or e["entry_hash"] != _entry_hash(e):
                return False
            prev = e["entry_hash"]
        return True

    # Protocol steps -----------------------------------------------------------

    def seal_ground_truth(self, sealed_file: Path, manifest_file: Path) -> Dict[str, Any]:
        return self.append(
            "seal_right_grid",
            sealed_sha256=sha256_file(sealed_file),
            public_manifest_sha256=sha256_file(manifest_file),
        )

    def current_epoch(self) -> List[Dict[str, Any]]:
        """Entries since the latest seal. Every evaluation run is one epoch: seal, commits, reveal."""
        chain = self.entries()
        starts = [i for i, e in enumerate(chain) if e["kind"] == "seal_right_grid"]
        return chain[starts[-1]:] if starts else []

    def commit_predictions(self, model_id: str, predictions_file: Path) -> Dict[str, Any]:
        if any(e["kind"] == "reveal_right_grid" for e in self.current_epoch()):
            raise RuntimeError("Right grid already revealed: late predictions are not blind and are refused.")
        return self.append("commit_left_grid", model_id=model_id, predictions_sha256=sha256_file(predictions_file))

    def reveal_ground_truth(self, sealed_file: Path) -> Dict[str, Any]:
        seals = [e for e in self.current_epoch() if e["kind"] == "seal_right_grid"]
        if not seals or seals[-1]["sealed_sha256"] != sha256_file(sealed_file):
            raise RuntimeError("Sealed right grid does not match its committed digest.")
        return self.append("reveal_right_grid", sealed_sha256=seals[-1]["sealed_sha256"])

    def committed_models(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for e in self.current_epoch():
            if e["kind"] == "reveal_right_grid":
                break
            if e["kind"] == "commit_left_grid":
                out[e["model_id"]] = e["predictions_sha256"]
        return out
