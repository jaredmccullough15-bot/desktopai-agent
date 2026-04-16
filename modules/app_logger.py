from __future__ import annotations

import os
from datetime import datetime


def append_agent_log(message: str, category: str = "System") -> None:
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(data_dir, "agent.log"), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {category}: {message}\n")
    except Exception:
        pass
