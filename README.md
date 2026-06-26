# Desktop AI Agent — Monorepo

## Source of Truth

| Directory | Purpose |
|---|---|
| `bill-core/` | FastAPI backend — AWS Elastic Beanstalk deployment |
| `bill-worker/` | Windows desktop worker — PyInstaller / auto-update |
| `bill-web/` | Next.js frontend — React / Tailwind |
| `tenant_templates/` | Tenant workflow JSON templates |
| `package-output/` | Build artifacts — worker ZIPs, installers |

**Do not develop from legacy root compatibility paths or `jarvis-platform/`.**
These exist only for backwards compatibility during transition and will be removed.

## Also in this repo

| Directory | Purpose |
|---|---|
| `archive/` | Archived legacy code — do not import from here |
| `backups/` | Manual backups |
| `data/` | Runtime data / sessions |

## Quick Start

- **Start Bill Core:** `start_core.bat`
- **Start Bill Worker:** `start_worker.ps1`
- **Package worker:** `bill-worker\package-worker.ps1`
- **Build installer:** `bill-worker\build-worker-installer.ps1`

## Manual Worker Deployment

Use the manual deployment script when you need to replace the running worker with a local package zip.

- **Run:** `powershell -ExecutionPolicy Bypass -File .\deploy_worker_manual.ps1 -PackagePath "C:\Ai Agent\desktop-ai-agent\package-output\bill-worker\bill-worker-complete.zip"`
- **What it does:**
	- Stops the running worker (uses stop script if present, otherwise path-scoped process stop)
	- Backs up current worker folder to `C:\JarvisWorkerBackup\<timestamp>`
	- Extracts and copies package files into `jarvis-platform\workers\bill-worker`
	- Preserves `config.json` when incoming package config appears to omit secrets
	- Starts the worker (`start_worker.ps1` or `start-worker.ps1`)
	- Tails logs for 30 seconds and verifies expected markers
- **Verification checks:**
	- `TEACH_TARGET_SELECTION_VERSION=2.0`
	- `SHOW_LEGACY_OBSERVATION_PANEL=False`
	- `TEACH_LEGACY_OBSERVATION_PANEL_DISABLED`
	- worker registration `status=200`
	- heartbeat `status=200`

If verification fails, the script prints the missing checks plus a restore command using the backup snapshot.

## Deployment Model

Production default:
- Amplify frontend -> Beanstalk bill-core backend -> Bill Workers
- Worker production `core_url` should target Beanstalk
- `api.bill-core.com` is treated as a legacy fallback endpoint, not the primary runtime path

Local development:
- You may use localhost/private-network URLs for backend testing
- LOCAL_DEV mode should be explicit in config/env and is separate from production assumptions

## Wave 1 Priority 3 Auth Variables

Bill Core shared-secret auth uses these backend variables:

- `BILL_CORE_AUTH_ENABLED` = `true` or `false`
- `BILL_CORE_AUTH_ALLOW_LOCAL_DEV` = `true` or `false`
- `BILL_CORE_DASHBOARD_API_KEY` = dashboard/server proxy key
- `BILL_CORE_WORKER_SHARED_SECRET` = worker shared secret

Frontend/Amplify server-side variable (do not expose with `NEXT_PUBLIC_`):

- `BILL_CORE_DASHBOARD_API_KEY`

Worker configuration supports either:

- Env override: `BILL_CORE_WORKER_SHARED_SECRET`
- `config.json` key: `worker_shared_secret`

## Bill Login Bootstrap

Bill Web now requires an employee login session for dashboard routes.

Set these backend environment variables before first startup to seed the first admin account:

- `BILL_CORE_ADMIN_EMAIL` (required to seed)
- `BILL_CORE_ADMIN_PASSWORD` (required to seed)
- `BILL_CORE_ADMIN_NAME` (optional, default `Bill Admin`)
- `BILL_CORE_ADMIN_ROLE` (optional, default `admin`)
- `BILL_CORE_ADMIN_TENANT_ID` (optional, default `default`)

After startup:

- Open Bill Web and sign in with the seeded admin credentials.
- Use the admin panel in the dashboard to create additional users and review audit entries.
