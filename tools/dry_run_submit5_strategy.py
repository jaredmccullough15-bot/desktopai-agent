import json
from pathlib import Path

manifest_path = Path("data/procedures/Submit 5/manifest.json")
if not manifest_path.exists():
    raise SystemExit("Submit 5 manifest not found")

data = json.loads(manifest_path.read_text(encoding="utf-8"))
events = sorted(data.get("events", []), key=lambda e: float(e.get("t", 0) or 0))


def infer_click_targets_from_expected_focus(expected_title: str):
    expected_clean = (expected_title or "").strip()
    expected = expected_clean.lower()
    expected = expected.replace(" - google chrome", "").strip()
    targets = []

    if expected:
        targets.append(expected.title())

    if "application status" in expected:
        targets.extend(["Application Status", "View status"])
    if "report a life change" in expected or "update application" in expected:
        targets.extend(["Report a life change", "Update application"])
    if "my account" in expected or "account homepage" in expected:
        targets.extend(["2026 Michigan application", "Michigan application", "2026 application", "Your applications"])
    if "protecting your personal information" in expected:
        targets.extend(["Continue", "Next"])
    if "review, sign, & submit" in expected:
        targets.extend(["Review, sign, & submit", "Continue"])

    if "log in" in expected or "sign in" in expected:
        targets.extend(["Log In", "Sign in", "Continue"])
    if "application setup" in expected or "savings setup" in expected:
        targets.extend(["Start application", "Continue", "Get started"])

    step_keywords = [
        "tell us about yourself",
        "home address",
        "mailing address",
        "contact information",
        "preferred language",
        "contact preferences",
        "application help",
        "who needs health coverage",
        "medicare enrollment",
        "marital status",
        "household tax returns",
        "parents & caretaker relatives",
        "household information",
        "race & ethnicity",
        "disabilities & help with activities",
        "medicaid or chip coverage ending",
        "recent household or income changes",
        "household income",
        "income for this month",
        "estimated income for this year",
        "current coverage & life changes",
        "current coverage",
        "job-based health coverage",
        "health reimbursement arrangements",
        "hra",
        "offers",
        "special enrollment period eligibility",
        "upcoming coverage changes",
        "life changes",
        "citizenship & immigration status",
        "personal & household information",
        "your marketplace application",
        "review your application",
        "read & agree to these statements",
        "sign & submit",
    ]
    if any(k in expected for k in step_keywords):
        targets.extend([
            "Continue",
            "Save & continue",
            "Next",
            "Confirm",
            "Submit",
        ])

    if "review your application" in expected:
        targets.extend(["Review, sign, & submit", "Continue"])
    if "read & agree" in expected or "sign & submit" in expected:
        targets.extend(["I agree", "Agree", "Sign & submit", "Submit"])

    dedup = []
    seen = set()
    for t in targets:
        cleaned = (t or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            dedup.append(cleaned)
    return dedup


print("Procedure:", data.get("name"))
print("=== Smart Click Dry-Run Plan (Submit 5) ===")

plan_rows = []
for i, ev in enumerate(events):
    if str(ev.get("type", "")).strip() != "click":
        continue

    cur_t = float(ev.get("t", 0) or 0)
    expected_focus = None
    expected_delta = None

    for j in range(i + 1, len(events)):
        nxt = events[j]
        if str(nxt.get("type", "")).strip() == "focus_window":
            next_t = float(nxt.get("t", 0) or 0)
            delta = max(0.0, next_t - cur_t)
            if delta <= 8.0:
                expected_focus = str(nxt.get("title", "")).strip()
                expected_delta = delta
            break

    if not expected_focus:
        continue

    targets = infer_click_targets_from_expected_focus(expected_focus)

    row = {
        "click_t": cur_t,
        "x": ev.get("x"),
        "y": ev.get("y"),
        "expected_delta": expected_delta,
        "expected_focus": expected_focus,
        "smart_targets": targets,
        "strategy": "smart-first" if targets else "coordinate-only",
    }
    plan_rows.append(row)

for row in plan_rows:
    print(f"\nclick@{row['click_t']:.3f} at ({row['x']},{row['y']})")
    print(f"  expected_next({row['expected_delta']:.3f}s): {row['expected_focus']}")
    print(f"  strategy: {row['strategy']}")
    if row['smart_targets']:
        print("  smart_targets:")
        for t in row['smart_targets']:
            print(f"    - {t}")

print("\n=== Summary ===")
smart_count = sum(1 for r in plan_rows if r["smart_targets"])
coord_count = sum(1 for r in plan_rows if not r["smart_targets"])
print(f"planned_click_checks: {len(plan_rows)}")
print(f"smart_first_clicks: {smart_count}")
print(f"coordinate_only_clicks: {coord_count}")
