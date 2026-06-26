# Bill Core System: Cloudflare/Tunnel Dependency Audit
**Date**: 2026-05-11  
**Status**: ⚠️ PARTIALLY MIGRATED (Cloudflare still primary default)

> Historical note (2026-05-18): This audit reflects an older runtime assumption set.
> Active production model is Amplify frontend -> Beanstalk backend -> Bill Workers.
> Cloudflare/tunnel references in this file should be treated as legacy context, not current production defaults.

---

## Executive Summary

The system is **partially migrated to Beanstalk**. While the worker correctly implements fallback logic (Cloudflare → Beanstalk), **Cloudflare URLs remain hardcoded as PRIMARY defaults in multiple locations**:

1. **Worker config files** still default to `https://api.bill-core.com` as `core_url`
2. **Backend teaching callbacks** default to `https://api.bill-core.com` 
3. **Backend worker updates** default to `https://api.bill-core.com` for package URLs
4. **Worker/update/check** and public URL generation use Cloudflare as default

**Result**: When systems are bootstrapped WITHOUT configuration override, they attempt Cloudflare first and only fall back to Beanstalk if Cloudflare fails.

---

## 1. BACKEND ANALYSIS

### ✅ Good: Teaching Mode API Base (Recently Fixed)
- **File**: [jarvis-platform/apps/bill-core/main.py](jarvis-platform/apps/bill-core/main.py#L272-L361)
- **Issue**: `_resolve_teach_session_worker_api_base()` now includes health checks
- **Behavior**:
  ```python
  DEFAULT_TEACH_SESSION_WORKER_API_BASE = "https://api.bill-core.com"
  DEFAULT_TEACH_SESSION_WORKER_API_FALLBACK = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
  ```
  - Probes Cloudflare `/health` → falls back to Beanstalk if HTTP 530 detected
  - Logs: `TEACHING_CALLBACK_API_BASE_SELECTED url=...`
- **Impact**: Teaching session callbacks now use working URL ✅

### ⚠️ Problem: Worker Update Package URLs
- **File**: [bill-core/main.py](bill-core/main.py#L540), [bill-core/main.py](bill-core/main.py#L583)
- **Line 540** - Package URL construction:
  ```python
  package_url_base = (os.getenv("BILL_CORE_PUBLIC_URL") or "https://api.bill-core.com").strip().rstrip("/")
  package_url = f"{package_url_base}/worker/update/package/{active_release.get('id', '')}"
  ```
- **Line 583** - Public URL for worker releases:
  ```python
  public_url = (os.getenv("BILL_CORE_PUBLIC_URL") or "https://api.bill-core.com").strip().rstrip("/")
  ```
- **Issue**: If `BILL_CORE_PUBLIC_URL` env var NOT set, worker update URLs default to Cloudflare
- **Impact**: Worker will try to fetch updates from `https://api.bill-core.com/worker/update/package/{id}` first

### ⚠️ Problem: Backend Health Endpoints
- **File**: [bill-core/main.py](bill-core/main.py#L8000+) (approx)
- **Routes**: `/health`, `/api/health`
- **Issue**: Backend serves health checks but Core is hardcoded as Cloudflare primary
- **Impact**: Workers that fail Cloudflare may not know Beanstalk is healthy without probing

---

## 2. WORKER ANALYSIS

### ✅ Good: URL Selection Logic
- **File**: [jarvis-platform/workers/bill-worker/main.py](jarvis-platform/workers/bill-worker/main.py#L627-L695)
- **Function**: `_select_active_core_url(primary, fallbacks)` and `_check_core_url_health()`
- **Behavior**:
  - Probes primary URL `/health` → if HTTP 530 or Cloudflare errors, tries fallbacks
  - Correctly detects CLOUDFLARE_TUNNEL_ERROR (HTTP 530, HTML body)
  - Falls back to Beanstalk if available
  - Logs: `CORE_URL_SELECTED url=... (primary|fallback)`
- **Status**: ✅ Works correctly

### ❌ Problem: PRIMARY DEFAULT is Still Cloudflare
- **File**: [jarvis-platform/workers/bill-worker/worker-config.json](jarvis-platform/workers/bill-worker/worker-config.json)
  ```json
  {
    "core_url": "https://api.bill-core.com",
    "fallback_core_urls": [
      "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
    ]
  }
  ```
- **Issue**: NEW workers starting will try Cloudflare first
- **Impact**: HTTP 530 errors → health check triggers → falls back to Beanstalk → works (but with delays)

### ✅ Good: Packaged Worker Has Fallbacks
- **File**: [package-output/bill-worker/config.json](package-output/bill-worker/config.json)
  ```json
  {
    "core_url": "https://api.bill-core.com",
    "fallback_core_urls": [
      "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
    ]
  }
  ```
- **Status**: ✅ Correctly includes Beanstalk fallback

### ⚠️ Problem: Build Script Defaults
- **File**: [jarvis-platform/workers/bill-worker/build-portable-worker.ps1](jarvis-platform/workers/bill-worker/build-portable-worker.ps1#L110-L125)
- **If source config.json exists**: Copies it (includes fallback)
- **If source config.json NOT found**: Generates default config:
  ```python
  "core_url": "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com",
  ```
  ✅ GOOD: Defaults to Beanstalk!
  - But: Does NOT include `fallback_core_urls` in generated config
  - Result: If built fresh, new worker won't have Cloudflare as fallback

### ✅ Good: Worker Update Check Uses Selected URL
- **File**: [jarvis-platform/workers/bill-worker/main.py](jarvis-platform/workers/bill-worker/main.py#L800+)
- **Behavior**: Worker check/register use the selected `API_BASE` (after health check)
- **Status**: ✅ Correctly uses active URL

---

## 3. FRONTEND ANALYSIS

### ✅ Good: Frontend Defaults to Beanstalk
- **File**: [app/page.tsx](app/page.tsx#L456)
  ```typescript
  const NEXT_PUBLIC_API_BASE_DEFAULT = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";
  ```
- **Env override**: `NEXT_PUBLIC_API_BASE` environment variable respected
- **Status**: ✅ Correctly points to Beanstalk

### ✅ Good: Environment Config
- **File**: [.env.local](.env.local#L1)
  ```
  NEXT_PUBLIC_API_BASE=http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com
  ```
- **Status**: ✅ Correctly set to Beanstalk

### ✅ Good: Voice/TTS/STT Endpoints
- **Files**: [app/hooks/useBillVoice.ts](app/hooks/useBillVoice.ts#L100)
- **Behavior**: Uses relative paths with dynamic `apiBase`, not hardcoded
- **Status**: ✅ Correctly routes through API base

---

## 4. BUILD & DEPLOYMENT SCRIPTS ANALYSIS

### ⚠️ Problem: Worker Config.json Not Updated During Packaging
- **File**: [jarvis-platform/workers/bill-worker/build-portable-worker.ps1](jarvis-platform/workers/bill-worker/build-portable-worker.ps1#L110-L125)
- **Copies source config**: If `config.json` exists, copies as-is
- **Does NOT generate fallbacks**: If no source, creates minimal config without `fallback_core_urls`
- **Workaround**: Current packaged workers manually patched with fallbacks

### ✅ Good: Beanstalk Used for Initial Build Default
- **Build script fallback logic**: Defaults to Beanstalk if no config found
- **Status**: ✅ Correct

### ✅ Good: Core Backend Deployment
- **File**: No hardcoded Cloudflare in EB packaging
- **Status**: ✅ Clean

---

## 5. RUNTIME BEHAVIOR MATRIX

| Component | Endpoint | Primary URL | Fallback | Status |
|-----------|----------|-------------|----------|--------|
| **Worker: Registration** | `/worker/register` | `https://api.bill-core.com` | ✅ Probes → falls back | Works (with delay) |
| **Worker: Heartbeat** | `/worker/heartbeat` | `https://api.bill-core.com` | ✅ Probes → falls back | Works (with delay) |
| **Worker: Task Poll** | `/worker/tasks/next` | `https://api.bill-core.com` | ✅ Probes → falls back | Works (with delay) |
| **Teaching Callback** | `/api/teaching/session/{id}/status` | `https://api.bill-core.com` | ✅ Probes → falls back | ✅ FIXED (health check) |
| **Worker Update Check** | `/worker/update/check` | Health-checked URL ✅ | N/A | ✅ Works |
| **Worker Update Package** | `/worker/update/package/{id}` | `BILL_CORE_PUBLIC_URL` or Cloudflare | N/A | ⚠️ Unprotected |
| **Frontend API Calls** | `/api/*` | Beanstalk ✅ | N/A | ✅ Works |
| **Voice Endpoints** | `/api/voice/*` | Beanstalk ✅ | N/A | ✅ Works |

---

## 6. HARDCODED Cloudflare/Tunnel REFERENCES

### Core Code References
1. **[bill-core/main.py:272](bill-core/main.py#L272)** - `DEFAULT_TEACH_SESSION_WORKER_API_BASE = "https://api.bill-core.com"`
2. **[bill-core/main.py:540](bill-core/main.py#L540)** - Worker package URL default
3. **[bill-core/main.py:583](bill-core/main.py#L583)** - Public URL default
4. **[jarvis-platform/apps/bill-core/main.py:272](jarvis-platform/apps/bill-core/main.py#L272)** - Same (mirror)
5. **[jarvis-platform/apps/bill-core/main.py:540](jarvis-platform/apps/bill-core/main.py#L540)** - Same (mirror)
6. **[jarvis-platform/apps/bill-core/main.py:583](jarvis-platform/apps/bill-core/main.py#L583)** - Same (mirror)

### Worker Config Files (Hardcoded Primary)
1. **[bill-worker/worker-config.json:2](bill-worker/worker-config.json#L2)** - `"core_url": "https://api.bill-core.com"`
2. **[jarvis-platform/workers/bill-worker/worker-config.json:2](jarvis-platform/workers/bill-worker/worker-config.json#L2)** - Same

### Environment Variable Defaults (If Not Overridden)
1. **`BILL_CORE_PUBLIC_URL`** - Falls back to `https://api.bill-core.com` if not set
2. **`BILL_CORE_WORKER_API_BASE`** - Falls back through chain if not set
3. **`BILL_CORE_URL`** - Falls back to Cloudflare if not set in config

### CORS/Validation (Not Runtime)
- Regex in [bill-core/main.py:176](bill-core/main.py#L176) allows `*.trycloudflare.com` URLs
  - This is for **validation only**, not a runtime dependency

---

## 7. CLOUDFLARE DETECTION/ERROR HANDLING

### ✅ Properly Detected
- [jarvis-platform/workers/bill-worker/main.py:638](jarvis-platform/workers/bill-worker/main.py#L638) - HTTP 530 detection
- [jarvis-platform/workers/bill-worker/main.py:639](jarvis-platform/workers/bill-worker/main.py#L639) - Cloudflare HTML body detection
- [jarvis-platform/apps/bill-core/main.py:299](jarvis-platform/apps/bill-core/main.py#L299) - HTTP 530 detection (new)
- [jarvis-platform/apps/bill-core/main.py:300](jarvis-platform/apps/bill-core/main.py#L300) - Cloudflare HTML body detection (new)

---

## 8. FINAL VERDICT

### Migration Status: **PARTIAL** (70% Complete)

**✅ Fully Migrated:**
- Frontend defaults to Beanstalk
- Teaching session callbacks now probe health before deciding
- Worker registration/heartbeat correctly fall back
- Voice endpoints use relative API base

**⚠️ Partially Migrated:**
- Worker config files still default to Cloudflare PRIMARY (fallback present)
- Backend teaching/public URLs still default to Cloudflare (fallback present)
- Worker update package URLs still default to Cloudflare if env var not set
- Build scripts don't automatically generate fallback URLs

**❌ Still Cloudflare-Dependent:**
- Without env var overrides or config modifications, NEW workers will attempt Cloudflare first
- Without `BILL_CORE_PUBLIC_URL` env var, worker update URLs use Cloudflare
- Without `BILL_CORE_WORKER_API_BASE` env var, teaching callbacks default to Cloudflare (but now with health check)

---

## 9. RECOMMENDED CLEANUP ORDER (Low → High Risk)

### Phase 1: LOW RISK (Safe to change immediately)
1. **Update worker-config.json defaults**
   - Change `"core_url": "https://api.bill-core.com"` → `"http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"`
   - Why: Workers already have fallback logic; changing primary to Beanstalk eliminates HTTP 530 attempts
   - Files: 
     - [bill-worker/worker-config.json](bill-worker/worker-config.json#L2)
     - [jarvis-platform/workers/bill-worker/worker-config.json](jarvis-platform/workers/bill-worker/worker-config.json#L2)

2. **Update build script default config**
   - Add `"fallback_core_urls": []` to generated config in [build-portable-worker.ps1](jarvis-platform/workers/bill-worker/build-portable-worker.ps1#L110)
   - Change primary to Beanstalk in generated config
   - Why: Ensures freshly-built workers aren't Cloudflare-dependent

### Phase 2: MEDIUM RISK (Requires env var setup, not code change)
1. **Set environment variables on deployment**
   - `BILL_CORE_PUBLIC_URL=http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com`
   - `BILL_CORE_WORKER_API_BASE=http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com`
   - Why: Overrides defaults without code changes
   - Target: EB deployment environment

### Phase 3: HIGH RISK (Changes defaults to non-Cloudflare)
1. **Change backend defaults**
   - [bill-core/main.py:272](bill-core/main.py#L272) - `DEFAULT_TEACH_SESSION_WORKER_API_BASE = "https://api.bill-core.com"` → Beanstalk
   - [jarvis-platform/apps/bill-core/main.py:272](jarvis-platform/apps/bill-core/main.py#L272) - Same (mirror)
   - Why: Removes Cloudflare from fallback chain; requires Cloudflare to stay unreachable
   - Risk: If Cloudflare is brought back online, system won't try it
   - Mitigate: Document explicitly that primary backend is Beanstalk only

---

## 10. DECISION MATRIX: Keep Cloudflare or Remove It?

### Option A: Keep Cloudflare as Primary (Current State)
**Pros:**
- Cloudflare can be brought back online as primary without code changes
- Fallback ensures Beanstalk is always available
- No risk of backward compatibility breaks

**Cons:**
- Adds HTTP 530 detection/fallback delay on every request
- Two URLs to maintain
- Confusing: Cloudflare is down but fallback works

### Option B: Switch to Beanstalk Primary, Keep Cloudflare Fallback
**Pros:**
- Eliminates HTTP 530 errors from primary attempts
- Faster startup (no health check needed)
- Cleaner mental model: Beanstalk is primary

**Cons:**
- Cloudflare becomes secondary; if brought back online, must change config
- Requires env var setup to override
- Slightly breaking if someone had Cloudflare hardcoded elsewhere

### Option C: Remove Cloudflare Entirely
**Pros:**
- Cleanest: Single backend
- No fallback logic needed
- Simplest codebase

**Cons:**
- If Cloudflare tunnel needs to be restored, requires code changes
- Cannot easily switch without recompile
- Breaks any external systems pointing to Cloudflare URLs

---

## 11. RECOMMENDED ACTION

**Recommendation: Option B — Switch to Beanstalk Primary, Keep Fallback**

1. **Phase 1** (immediate, low risk):
   - Update worker-config.json to default to Beanstalk
   - Update build script to generate Beanstalk-primary config
   - Cost: ~5 minutes, 4 files

2. **Phase 2** (deployment):
   - Set env vars on EB: `BILL_CORE_PUBLIC_URL`, `BILL_CORE_WORKER_API_BASE`
   - Cost: ~2 minutes, no code changes

3. **Phase 3** (optional, 6+ months):
   - Once Cloudflare tunnel is confirmed permanently down, remove fallback logic
   - Cost: ~30 minutes, cleanup pass

**Result**: System runs faster (no HTTP 530 attempts), still has fallback if needed, minimal risk.

---

## Summary Table: All Remaining Cloudflare References

| Reference | Type | File | Line | Severity | Risk |
|-----------|------|------|------|----------|------|
| `DEFAULT_TEACH_SESSION_WORKER_API_BASE` | Code default | bill-core/main.py | 272 | ⚠️ | Now has fallback ✅ |
| `package_url_base` default | Code default | bill-core/main.py | 540 | ⚠️ | Env override available |
| `public_url` default | Code default | bill-core/main.py | 583 | ⚠️ | Env override available |
| worker-config.json primary | Config file | worker-config.json | 2 | ⚠️ | Fallback present ✅ |
| Build script default config | Script logic | build-portable-worker.ps1 | 110 | ⚠️ | No fallback if generated |
| CORS regex pattern | Validation | bill-core/main.py | 176 | ✅ | Not runtime |
| HTTP 530 detection | Handler | worker/bill-worker/main.py | 638 | ✅ | Works correctly |
| Cloudflare error detection | Handler | bill-core/main.py | 299 | ✅ | Works correctly |

---

**Audit Complete**
