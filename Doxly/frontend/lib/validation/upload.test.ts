import { describe, expect, it } from "vitest";
import { validateFileForUpload } from "./upload";
import { MAX_FILE_SIZE_BYTES } from "@/lib/constants/documents";

function makeFile(name: string, type: string, size: number): File {
  const file = new File([new Uint8Array(Math.min(size, 1024))], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("validateFileForUpload — FR-DOC-001", () => {
  it("accepts a supported type under the size limit", () => {
    const file = makeFile("invoice.pdf", "application/pdf", 1024);
    expect(validateFileForUpload(file)).toBeNull();
  });

  it("rejects an unsupported type client-side, before any network call", () => {
    const file = makeFile("archive.zip", "application/zip", 1024);
    expect(validateFileForUpload(file)).toMatch(/unsupported file type/i);
  });

  it("rejects a file over the 25MB limit (decisions.md OQ-06)", () => {
    const file = makeFile("huge.pdf", "application/pdf", MAX_FILE_SIZE_BYTES + 1);
    expect(validateFileForUpload(file)).toMatch(/exceeds/i);
  });

  it("accepts a file exactly at the size limit", () => {
    const file = makeFile("max.pdf", "application/pdf", MAX_FILE_SIZE_BYTES);
    expect(validateFileForUpload(file)).toBeNull();
  });

  it("rejects an empty file", () => {
    const file = makeFile("empty.pdf", "application/pdf", 0);
    expect(validateFileForUpload(file)).toMatch(/empty/i);
  });

  it("falls back to extension matching when the browser reports no MIME type", () => {
    const file = makeFile("notes.csv", "", 1024);
    expect(validateFileForUpload(file)).toBeNull();
  });
});
