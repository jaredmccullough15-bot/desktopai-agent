from __future__ import annotations

import argparse
import json
import os
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a task to Jarvis shared memory hub queue")
    parser.add_argument("--machine-id", required=True, help="Target machine id (example: Jared@Workstation1)")
    parser.add_argument("--site", required=True, help="Site key, e.g. healthsherpa.com")
    parser.add_argument("--task-type", required=True, help="Task type, e.g. smart_sync")
    parser.add_argument("--start-url", required=True, help="Start URL for worker")
    parser.add_argument("--goal", required=True, help="Human-readable goal")
    parser.add_argument("--input-json", default="{}", help="Optional JSON input payload")
    parser.add_argument("--api", default=os.getenv("JARVIS_MEMORY_API", "http://127.0.0.1:8787"), help="Memory API base URL")
    args = parser.parse_args()

    try:
        input_data = json.loads(args.input_json or "{}")
    except Exception as exc:
        raise SystemExit(f"Invalid --input-json: {exc}")

    payload = {
        "machine_id": args.machine_id,
        "site": args.site,
        "task_type": args.task_type,
        "start_url": args.start_url,
        "goal": args.goal,
        "input_data": input_data,
    }

    url = args.api.rstrip("/") + "/tasks"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
