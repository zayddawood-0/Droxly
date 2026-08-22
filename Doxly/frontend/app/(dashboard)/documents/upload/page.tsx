import type { Metadata } from "next";
import { UploadView } from "./upload-view";

export const metadata: Metadata = { title: "Upload a document" };

export default function UploadPage() {
  return <UploadView />;
}
