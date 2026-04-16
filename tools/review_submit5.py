import json
from pathlib import Path

manifest_path = Path("data/procedures/Submit 5/manifest.json")
data = json.loads(manifest_path.read_text(encoding="utf-8"))
events = sorted(data.get("events", []), key=lambda e: float(e.get("t", 0) or 0))

signatures = {
    "login": ["log in", "sign in"],
    "account_home": ["account homepage", "my account"],
    "application_status": ["application status"],
    "life_change": ["report a life change", "update application"],
    "privacy_notice": ["protecting your personal information"],
    "marketplace_application": ["your marketplace application", "application setup", "savings setup"],
}


def classify_title(title: str):
    t = (title or "").lower()
    return [name for name, keys in signatures.items() if any(key in t for key in keys)]

focus_events = [e for e in events if e.get("type") == "focus_window"]
click_events = [e for e in events if e.get("type") == "click"]
scroll_events = [e for e in events if e.get("type") == "scroll"]

print("Procedure:", data.get("name"))
print("focus_count:", len(focus_events))
print("click_count:", len(click_events))
print("scroll_count:", len(scroll_events))
print("empty_hint_clicks:", sum(1 for e in click_events if not str(e.get("hint_text", "")).strip()))

print("\n=== Focus Timeline ===")
for f in focus_events:
    t = float(f.get("t", 0) or 0)
    title = str(f.get("title", ""))
    print(f"{t:6.3f} | {title[:95]} | classes={classify_title(title)}")

print("\n=== Click -> Next Focus (<=10s) ===")
for i, e in enumerate(events):
    if e.get("type") != "click":
        continue
    t = float(e.get("t", 0) or 0)
    nxt = None
    for j in range(i + 1, len(events)):
        if events[j].get("type") == "focus_window":
            nxt = events[j]
            break
    if not nxt:
        continue
    dt = float(nxt.get("t", 0) or 0) - t
    if dt <= 10:
        print(f"click@{t:6.3f} -> {dt:5.3f}s -> {str(nxt.get('title', ''))[:80]}")

print("\n=== Potential Fragility Flags ===")
if sum(1 for e in click_events if not str(e.get("hint_text", "")).strip()) > 5:
    print("- Most clicks have no hint_text; replay depends heavily on coordinates.")

# Find account-home click step specifically
for i, f in enumerate(focus_events):
    title = str(f.get("title", "")).lower()
    if "account homepage" in title or "my account" in title:
        t0 = float(f.get("t", 0) or 0)
        next_click = None
        for ev in events:
            if float(ev.get("t", 0) or 0) > t0 and ev.get("type") == "click":
                next_click = ev
                break
        if next_click:
            print(f"- First post-account click is coordinate-only at t={float(next_click.get('t',0)):0.3f} x={next_click.get('x')} y={next_click.get('y')}")
        break
