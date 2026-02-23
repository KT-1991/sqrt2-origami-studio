from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List


def make_run_request_entry(
    *,
    profile_name: str,
    request: Dict[str, object],
) -> Dict[str, object]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profile_name": profile_name,
        "request": request,
    }


def load_run_request_payload(path: str) -> List[Dict[str, object]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        existing = json.load(f)
    if isinstance(existing, list):
        if not all(isinstance(x, dict) for x in existing):
            raise ValueError("run-request JSON list must contain only objects")
        return list(existing)
    if isinstance(existing, dict):
        return [existing]
    raise ValueError("run-request JSON must be an object or an array of objects")


def append_run_request(path: str, entry: Dict[str, object]) -> None:
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    payload = load_run_request_payload(path)
    payload.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
