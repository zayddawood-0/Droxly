"use client";

import { useState } from "react";
import Link from "next/link";
import { Upload, Sparkles, Search } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentCard } from "@/components/domain/documents/document-card";
import { DocumentsEmptyState } from "@/components/domain/documents/documents-empty-state";
import { UsageStrip } from "@/components/domain/documents/usage-strip";
import { UploadDialog } from "@/components/domain/documents/upload-dialog";
import { useDocumentsQuery } from "@/hooks/use-documents";

const RECENT_LIMIT = 5;

export function DashboardView() {
  const [uploadOpen, setUploadOpen] = useState(false);
  const query = useDocumentsQuery({ limit: RECENT_LIMIT, sort: "created_at_desc" });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold sm:text-2xl">Welcome back</h1>
        <UsageStrip />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <QuickAction
          icon={Upload}
          label="Upload a document"
          onClick={() => setUploadOpen(true)}
        />
        <QuickAction icon={Sparkles} label="Ask a question" href="/chat" />
        <QuickAction icon={Search} label="Search your documents" href="/search" />
      </div>

      <section aria-labelledby="recent-documents-heading">
        <h2 id="recent-documents-heading" className="mb-3 text-sm font-medium text-muted-foreground">
          Recent documents
        </h2>

        {query.isPending ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-lg" />
            ))}
          </div>
        ) : query.isError ? (
          <div className="flex items-center justify-between rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
            Couldn&apos;t load your recent documents.
            <Button variant="ghost" size="sm" onClick={() => query.refetch()}>
              Retry
            </Button>
          </div>
        ) : query.data.items.length === 0 ? (
          <DocumentsEmptyState variant="no-documents" onUpload={() => setUploadOpen(true)} />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {query.data.items.map((doc) => (
              <DocumentCard key={doc.id} document={doc} compact />
            ))}
          </div>
        )}
      </section>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </div>
  );
}

function QuickAction({
  icon: Icon,
  label,
  href,
  onClick,
}: {
  icon: typeof Upload;
  label: string;
  href?: string;
  onClick?: () => void;
}) {
  const content = (
    <Card className="flex flex-row items-center gap-3 p-4 transition-colors hover:border-muted-foreground/40">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Icon className="size-4" aria-hidden="true" />
      </div>
      <span className="text-sm font-medium">{label}</span>
    </Card>
  );

  if (href) {
    return (
      <Link
        href={href}
        className="block rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        aria-label={label}
      >
        {content}
      </Link>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={onClick}
      onKeyDown={(event) => {
        if (onClick && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          onClick();
        }
      }}
      className="cursor-pointer rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {content}
    </div>
  );
}
