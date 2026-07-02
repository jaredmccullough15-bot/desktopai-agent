import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const DEFAULT_BACKEND = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";
const DEPRECATED_BACKEND_HOSTS = new Set(["api.bill-core.com", "core.bill-core.com"]);

function isDeprecatedBackend(value: string): boolean {
  try {
    const hostname = new URL(value).hostname.toLowerCase();
    return DEPRECATED_BACKEND_HOSTS.has(hostname);
  } catch {
    return false;
  }
}

function resolveBackendBase(): string {
  const candidates = [
    process.env.BILL_CORE_API_BASE,
    process.env.NEXT_PUBLIC_API_BASE,
  ];

  for (const raw of candidates) {
    const value = (raw ?? "").trim().replace(/\/$/, "");
    if (!value) continue;
    if (value.startsWith("/api/proxy")) continue;

    try {
      const parsed = new URL(value);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        if (isDeprecatedBackend(value)) {
          continue;
        }
        return value;
      }
    } catch {
      // Ignore invalid backend values.
    }
  }

  return DEFAULT_BACKEND;
}

export async function GET() {
  const dashboardApiKey = (process.env.BILL_CORE_DASHBOARD_API_KEY ?? "").trim();
  const backendBase = resolveBackendBase();

  return NextResponse.json(
    {
      proxy_runtime: true,
      dashboard_key_present: dashboardApiKey.length > 0,
      backend_base: backendBase,
      node_env: process.env.NODE_ENV ?? "unknown",
      timestamp: new Date().toISOString(),
    },
    {
      headers: {
        "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
      },
    }
  );
}
