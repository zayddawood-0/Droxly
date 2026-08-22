"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { getDocumentStatus, type DocumentDetail, type DocumentStatus } from "@/lib/api/documents";

const TERMINAL_STATUSES: DocumentStatus[] = ["ready", "failed"];
const POLL_INTERVAL_MS = 3000;

type StatusPayload = { status: DocumentStatus; processing_error: string | null };

/**
 * FR-DOC-008: live pipeline status in the Document Viewer "without a full
 * page reload (polling or SSE)" (requirements.md). Prefers GET
 * .../status/stream (api.md §"documents"); if the connection errors — the
 * expected outcome against this frontend-only track's backend-less BFF,
 * and a real-world reconnect path too — falls back to polling GET
 * .../status on the same interval, per the endpoint's documented "SSE
 * where supported, polling fallback" contract. Writes land directly in the
 * TanStack Query cache so StatusBadge/DocumentContentPane re-render from
 * the same `useDocumentQuery` data everywhere else in the tree already
 * reads from — no second source of truth for status.
 */
export function useDocumentStatusStream(
  documentId: string,
  status: DocumentStatus | undefined,
  pollIntervalMs = POLL_INTERVAL_MS,
) {
  const queryClient = useQueryClient();
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!status || TERMINAL_STATUSES.includes(status)) return;

    let cancelled = false;

    function applyStatus(next: StatusPayload) {
      queryClient.setQueryData<DocumentDetail | undefined>(
        ["documents", "detail", documentId],
        (prev) => (prev ? { ...prev, ...next } : prev),
      );
      if (TERMINAL_STATUSES.includes(next.status)) {
        queryClient.invalidateQueries({ queryKey: ["documents"] });
        stopPolling();
      }
    }

    function stopPolling() {
      if (pollTimer.current) {
        clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
    }

    function startPolling() {
      if (pollTimer.current || cancelled) return;
      pollTimer.current = setInterval(async () => {
        try {
          const next = await getDocumentStatus(documentId);
          if (!cancelled) applyStatus(next);
        } catch {
          // Transient — the next tick tries again rather than surfacing a
          // toast for what's a background refresh, not a user action.
        }
      }, pollIntervalMs);
    }

    const source = new EventSource(`/api/v1/documents/${documentId}/status/stream`);
    source.addEventListener("status", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent<string>).data) as StatusPayload;
        applyStatus(data);
      } catch {
        // Malformed event — the polling fallback below still covers us.
      }
    });
    source.onerror = () => {
      source.close();
      startPolling();
    };

    return () => {
      cancelled = true;
      source.close();
      stopPolling();
    };
  }, [documentId, status, queryClient, pollIntervalMs]);
}
