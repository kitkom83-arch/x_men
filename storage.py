from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

ENV_PATH = Path(".env")


def read_env(path: Path = ENV_PATH) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def write_env(values: Dict[str, str], path: Path = ENV_PATH) -> None:
    current = read_env(path)
    current.update({k: str(v) for k, v in values.items()})
    lines = [f"{k}={v}" for k, v in current.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
