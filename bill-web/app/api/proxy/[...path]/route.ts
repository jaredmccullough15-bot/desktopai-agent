import { NextRequest, NextResponse } from "next/server";

const BACKEND =
  (process.env.NEXT_PUBLIC_API_BASE?.trim()?.replace(/\/$/, "")) ||
  "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";

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
    return new NextResponse(data, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") || "application/octet-stream" },
    });
  } catch (err) {
    return NextResponse.json({ error: "Proxy error", detail: String(err) }, { status: 502 });
  }
}
