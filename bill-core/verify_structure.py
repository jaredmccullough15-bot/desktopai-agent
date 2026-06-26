import os

required = [
    "main.py",
    "task_service.py",
    "conversational",
    "conversational/__init__.py"
]

for path in required:
    if not os.path.exists(path):
        print(f"Missing: {path}")
    else:
        print(f"OK: {path}")
