import type { Metadata } from "next";
import { DocumentViewer } from "./document-viewer";

export const metadata: Metadata = { title: "Document" };

export default async function DocumentViewerPage({
  params,
}: {
  params: Promise<{ documentId: string }>;
}) {
  const { documentId } = await params;
  return <DocumentViewer documentId={documentId} />;
}
