import { fetchWithRefresh } from "@/lib/api/client";
import { DoxlyApiError, type ApiErrorBody } from "@/lib/types/errors";

export type SSEEventHandler = (event: string, data: unknown) => void;

/**
 * Consumes a `text/event-stream` response by POSTing a body (api.md §4's
 * chat streaming contract) — native `EventSource` can't be used here since
 * it only supports GET with no body. Reuses `fetchWithRefresh` so the
 * session-refresh/CSRF logic in lib/api/client.ts has exactly one
 * implementation, never duplicated for the streaming path.
 *
 * Per api.md: "Errors returned as standard JSON before the stream opens,
 * not as an SSE event" — a non-2xx response throws a DoxlyApiError just
 * like `apiFetch`, so callers use the same `isConnectivityError` handling
 * everywhere else in the app. Once the stream itself opens, each parsed
 * `event: <type>` / `data: <json>` pair is handed to `onEvent` — including
 * a possible `event: error` mid-stream, which is data the caller
 * interprets, not a thrown exception (the stream already succeeded in
 * opening; a mid-stream error is a business outcome, not a transport failure).
 */
export async function consumeEventStream(
  path: string,
  body: unknown,
  onEvent: SSEEventHandler,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetchWithRefresh(path, { method: "POST", body, signal });

  if (!response.ok) {
    const isJson = response.headers.get("content-type")?.includes("application/json");
    const payload = isJson ? await response.json() : undefined;
    throw new DoxlyApiError(response.status, payload as ApiErrorBody);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new DoxlyApiError(response.status, {
      error: { code: "stream_unavailable", message: "The response body could not be read." },
    });
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const rawEvents = buffer.split("\n\n");
    buffer = rawEvents.pop() ?? "";

    for (const rawEvent of rawEvents) {
      const parsed = parseEvent(rawEvent);
      if (parsed) onEvent(parsed.event, parsed.data);
    }
  }

  const trailing = parseEvent(buffer);
  if (trailing) onEvent(trailing.event, trailing.data);
}

function parseEvent(raw: string): { event: string; data: unknown } | null {
  const eventLine = raw.split("\n").find((line) => line.startsWith("event: "));
  const dataLine = raw.split("\n").find((line) => line.startsWith("data: "));
  if (!eventLine || !dataLine) return null;

  try {
    return {
      event: eventLine.slice("event: ".length).trim(),
      data: JSON.parse(dataLine.slice("data: ".length)),
    };
  } catch {
    return null;
  }
}
