# Bill Worker Setup (Windows LAN Test)

Use the generated single ZIP package so the user downloads one file only.

## Windows installer build (recommended distribution)
- In this folder, run:

`powershell -ExecutionPolicy Bypass -File .\build-worker-installer.ps1`

- The script auto-installs Inno Setup via `winget` when possible.
- If auto-install fails, install Inno Setup manually: https://jrsoftware.org/isdl.php

- Output installer:

`package-output\installer\bill-worker-setup-1.0.0.exe`

- The installer flow keeps ZIP backups automatically.

## Build one-file package (on your machine)
- In this folder, run:

`powershell -ExecutionPolicy Bypass -File .\package-worker.ps1`

- Output file:

`package-output\bill-worker-complete.zip`

- This complete ZIP attempts to include:
	- Worker code and scripts
	- Playwright browser cache (if found)
	- Offline wheelhouse for requirements (if download succeeds)

Note: `.venv` is intentionally not packaged because Windows virtual environments are machine-specific.
`start-worker.ps1` creates a local `.venv` on the target machine automatically.

- Optional smaller package:

`powershell -ExecutionPolicy Bypass -File .\package-worker.ps1 -Lite`

## 1) Copy to the other computer
- Copy only `bill-worker-complete.zip` to the other PC.
- Extract it to any folder.

## 2) Start the worker
- Open PowerShell in the extracted `bill-worker` folder.
- Run:

`powershell -ExecutionPolicy Bypass -File .\start-worker.ps1`

Startup behavior:
- Reuses existing components if already present.
- Uses bundled browsers/wheels when included.
- Installs only missing dependencies.
- Attempts to auto-install Python via `winget` if Python is missing.

## 3) What success looks like
- The script prints that Core health check passed.
- The worker starts and sends heartbeats.
- The worker appears in the Bill/Jarvis dashboard machine list.
- Sending a visible browser task opens a browser window on that worker PC.

## 4) Configure before starting (optional)
Edit `worker-config.json` if needed:
- `core_url` (default: `http://192.168.30.88:8000`)
- `machine_display_name`
- `default_execution_mode` (`interactive_visible` by default)
- `heartbeat_interval_seconds`
- `polling_interval_seconds`
- `screenshots_dir`
- `downloads_dir`

You can also override with environment variables.

## 5) Troubleshooting
### Health check URL
Test from worker PC browser:

`http://192.168.30.88:8000/health`

Expected result:

`{"status":"ok"}`

### If worker cannot connect
- Core may not be running.
- Core IP may be wrong.
- Firewall may block port 8000.
- Core may be bound only to localhost.

On the main machine, start Core like this:

`python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000`

### Visible mode note
When running visible automation, avoid using the worker desktop at the same time.

## 6) Secrets
- `secrets.local.json` is local-only and should not be committed.
- Use `secrets.example.json` as a template.
- Copy `secrets.example.json` to `secrets.local.json` and fill real values only on the worker machine.
