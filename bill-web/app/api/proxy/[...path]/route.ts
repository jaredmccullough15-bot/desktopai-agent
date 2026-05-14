import { NextRequest, NextResponse } from "next/server";

const DEFAULT_BACKEND = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";

function resolveBackendBase(): string {
  const candidates = [
    process.env.BILL_CORE_API_BASE,
    process.env.NEXT_PUBLIC_API_BASE,
  ];

  for (const raw of candidates) {
    const value = (raw ?? "").trim().replace(/\/$/, "");
    if (!value) {
      continue;
    }

    // Prevent recursive proxying when env is set to "/api/proxy".
    if (value.startsWith("/api/proxy")) {
      continue;
    }

    try {
      const parsed = new URL(value);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        return value;
      }
    } catch {
      // Ignore non-absolute values.
    }
  }

  return DEFAULT_BACKEND;
}

const BACKEND = resolveBackendBase();

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, "GET");
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, "POST");
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, "PUT");
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, "DELETE");
}

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string
) {
  const path = pathSegments.join("/");
  const search = request.nextUrl.search;
  const url = `${BACKEND}/${path}${search}`;

  const headers: Record<string, string> = {};
  const requestContentType = request.headers.get("content-type");
  if (requestContentType) {
    headers["Content-Type"] = requestContentType;
  }
  const authHeader = request.headers.get("authorization");
  if (authHeader) headers["authorization"] = authHeader;

  const dashboardApiKey = (process.env.BILL_CORE_DASHBOARD_API_KEY ?? "").trim();
  if (dashboardApiKey) {
    // Inject only on the server proxy; never expose this key to the browser.
    headers["X-Bill-Core-Key"] = dashboardApiKey;
    console.log(`[auth-proxy] Dashboard key present=true, path=${path}, method=${method}`);
  } else {
    console.warn(`[auth-proxy] WARNING: Dashboard key missing! path=${path}, method=${method}`);
  }

  let body: string | undefined;
  if (method !== "GET" && method !== "DELETE") {
    try {
      body = await request.text();
    } catch {
      /* no body */
    }
  }

  try {
    const response = await fetch(url, {
      method,
      headers,
      body,
    });
    const data = await response.arrayBuffer();
    console.log(`[auth-proxy] Response: status=${response.status}, path=${path}, method=${method}`);
    return new NextResponse(data, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/octet-stream" },
    });
  } catch (err) {
    console.error(`[auth-proxy] Proxy error: ${String(err)}, path=${path}, method=${method}`);
    return NextResponse.json({ error: "Proxy error", detail: String(err) }, { status: 502 });
  }
}
