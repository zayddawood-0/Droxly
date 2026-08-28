import { NextRequest, NextResponse } from "next/server";

/**
 * The thin BFF proxy — the only place this app talks to FastAPI
 * (specs/architecture.md §2.1). Every request under /api/v1/* is forwarded
 * to INTERNAL_API_URL with cookies relayed unmodified in both directions;
 * this file must never grow business logic (skills/devops.md's Vercel
 * guidance: "if a handler is doing anything more than forwarding a
 * request/relaying cookies, that's a signal it belongs in FastAPI instead").
 *
 * Every domain module under lib/api/ (auth, documents, chat, ...) routes
 * through this proxy, including the chat SSE stream (lib/api/chat.ts) --
 * `upstream.body` is passed straight through to `NextResponse` unbuffered,
 * so a streamed FastAPI response streams to the browser as-is. The browser
 * never calls the FastAPI origin directly for anything except a presigned
 * storage upload (specs/deployment.md §1's topology diagram / §7).
 */

async function proxy(request: NextRequest, path: string[]) {
  const backendOrigin = process.env.INTERNAL_API_URL;
  if (!backendOrigin) {
    return NextResponse.json(
      {
        error: {
          code: "backend_not_configured",
          message: "The API is not reachable right now. Please try again shortly.",
        },
      },
      { status: 502 },
    );
  }

  const requestId = request.headers.get("x-request-id") ?? crypto.randomUUID();
  const targetUrl = `${backendOrigin}/api/v1/${path.join("/")}${request.nextUrl.search}`;

  const forwardHeaders = new Headers();
  const cookie = request.headers.get("cookie");
  if (cookie) forwardHeaders.set("cookie", cookie);
  const contentType = request.headers.get("content-type");
  if (contentType) forwardHeaders.set("content-type", contentType);
  const csrfToken = request.headers.get("x-csrf-token");
  if (csrfToken) forwardHeaders.set("x-csrf-token", csrfToken);
  forwardHeaders.set("x-request-id", requestId);

  const hasBody = request.method !== "GET" && request.method !== "DELETE";

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers: forwardHeaders,
      body: hasBody ? await request.text() : undefined,
      redirect: "manual",
    });
  } catch {
    // Never leak internal detail (fetch/DNS/connection errors) to the client
    // — specs/security.md §11.2's sanitized-error-envelope principle applied
    // at the BFF layer, not only inside FastAPI.
    return NextResponse.json(
      {
        error: {
          code: "upstream_unavailable",
          message: "The API is not reachable right now. Please try again shortly.",
        },
      },
      { status: 502, headers: { "x-request-id": requestId } },
    );
  }

  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.set("x-request-id", requestId);

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

function makeHandler() {
  return async (
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> },
  ) => {
    const { path } = await params;
    return proxy(request, path);
  };
}

export const GET = makeHandler();
export const POST = makeHandler();
export const PATCH = makeHandler();
export const PUT = makeHandler();
export const DELETE = makeHandler();
