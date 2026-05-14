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
