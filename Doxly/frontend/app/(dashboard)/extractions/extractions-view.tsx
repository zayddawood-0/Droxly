"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { FileSearch, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentPicker } from "@/components/domain/documents/document-picker";
import { TemplateGallery } from "@/components/domain/extractions/template-gallery";
import { SchemaBuilder } from "@/components/domain/extractions/schema-builder";
import { useDocumentExtractionsQuery, useCreateExtractionMutation } from "@/hooks/use-extractions";
import { useDocumentQuery } from "@/hooks/use-documents";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";
import type { SchemaField } from "@/lib/api/extractions";

type Mode = "template" | "custom";

/**
 * ui-ux.md §10 — "Document + schema selection step... followed by a
 * results view" (the results view is the [extractionId] route). No
 * dedicated document context is required to arrive here (reachable from
 * the sidebar directly) — the document picker is the first step when
 * `?document=` isn't already set (e.g. by Document Viewer's "Extract"
 * action).
 */
export function ExtractionsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const documentId = searchParams.get("document");

  const [mode, setMode] = useState<Mode>("template");
  const [templateKey, setTemplateKey] = useState<string | null>(null);
  const [customFields, setCustomFields] = useState<SchemaField[]>([
    { name: "", type: "string", required: false },
  ]);

  const documentQuery = useDocumentQuery(documentId ?? "");
  const historyQuery = useDocumentExtractionsQuery(documentId);
  const createMutation = useCreateExtractionMutation();

  function selectDocument(id: string) {
    router.replace(`/extractions?document=${id}`, { scroll: false });
  }

  async function handleRun() {
    if (!documentId) return;
    try {
      const input =
        mode === "template" && templateKey
          ? { document_id: documentId, template_key: templateKey }
          : { document_id: documentId, schema: customFields.filter((f) => f.name.trim()) };
      const created = await createMutation.mutateAsync(input);
      router.push(`/extractions/${created.id}`);
    } catch (error) {
      toast.error(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Couldn't start this extraction. Please try again.",
      );
    }
  }

  const canRun =
    mode === "template"
      ? Boolean(templateKey)
      : customFields.some((field) => field.name.trim().length > 0);

  if (!documentId) {
    return (
      <div className="mx-auto flex max-w-md flex-col gap-3 rounded-lg border border-dashed border-border px-6 py-12 text-center">
        <FileSearch className="mx-auto size-6 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium">Choose a document to extract from</p>
        <DocumentPicker selectedId={null} onChange={selectDocument} placeholder="Select a document…" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">Document</p>
          <p className="truncate text-sm font-medium">
            {documentQuery.isPending ? "Loading…" : (documentQuery.data?.file_name ?? "Unknown document")}
          </p>
        </div>
        <div className="w-64 shrink-0">
          <DocumentPicker selectedId={documentId} onChange={selectDocument} />
        </div>
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Past extractions</h2>
        </div>
        {historyQuery.isPending ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        ) : historyQuery.isError ? (
          <div className="flex items-center justify-between rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
            Couldn&apos;t load past extractions.
            <Button variant="ghost" size="sm" onClick={() => historyQuery.refetch()}>
              Retry
            </Button>
          </div>
        ) : historyQuery.data.items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
            No extractions yet for this document — run one below.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {historyQuery.data.items.map((extraction) => (
              <li key={extraction.id}>
                <Link
                  href={`/extractions/${extraction.id}`}
                  className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm outline-none hover:bg-accent/50 focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <span>{humanizeTemplateKey(extraction.template_key)}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {new Date(extraction.created_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold">New extraction</h2>
        {mode === "template" ? (
          <TemplateGallery
            selectedKey={templateKey}
            onSelect={setTemplateKey}
            onSelectCustom={() => setMode("custom")}
          />
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">Define the fields to extract.</p>
              <Button variant="ghost" size="sm" onClick={() => setMode("template")}>
                Use a template instead
              </Button>
            </div>
            <SchemaBuilder fields={customFields} onChange={setCustomFields} />
          </div>
        )}

        <Button type="button" onClick={handleRun} disabled={!canRun || createMutation.isPending} className="mt-4">
          {createMutation.isPending && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
          Run extraction
        </Button>
      </section>
    </div>
  );
}

function humanizeTemplateKey(templateKey: string | null): string {
  if (!templateKey) return "Custom schema";
  return templateKey
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
