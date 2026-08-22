import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { mswServer } from "@/lib/test/msw-server";
import { UploadDialog } from "./upload-dialog";

function renderWithQueryClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("UploadDialog — FR-DOC-001 end-to-end", () => {
  it("runs presign → direct PUT → confirm, and shows the file as queued", async () => {
    mswServer.use(
      http.post("/api/v1/documents/presign", () =>
        HttpResponse.json(
          {
            document_id: "doc_1",
            upload_url: "https://storage.example.com/upload/doc_1",
            upload_method: "PUT",
            upload_headers: {},
            expires_in: 900,
          },
          { status: 201 },
        ),
      ),
      http.put("https://storage.example.com/upload/doc_1", () => new HttpResponse(null, { status: 200 })),
      http.post("/api/v1/documents/doc_1/confirm", () =>
        HttpResponse.json({ id: "doc_1", status: "queued" }, { status: 202 }),
      ),
    );

    const user = userEvent.setup();
    renderWithQueryClient(<UploadDialog open onOpenChange={() => {}} />);

    const file = new File(["content"], "invoice.pdf", { type: "application/pdf" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    expect(await screen.findByText("invoice.pdf")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("Queued for processing")).toBeInTheDocument(),
    );
  });

  it("shows a specific rejection reason for an unsupported file, without any network call", async () => {
    mswServer.use(
      http.post("/api/v1/documents/presign", () => {
        throw new Error("should not be called for a rejected file");
      }),
    );

    // The dropzone's <input accept> is only a browser file-picker hint —
    // a user can still pick "All Files" and select a .zip. user-event
    // emulates that filtering by default, so it must be disabled here to
    // exercise the app's own client-side rejection, not the browser's.
    const user = userEvent.setup({ applyAccept: false });
    renderWithQueryClient(<UploadDialog open onOpenChange={() => {}} />);

    const file = new File(["content"], "archive.zip", { type: "application/zip" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    expect(await screen.findByText(/unsupported file type/i)).toBeInTheDocument();
  });

  it("one file's upload failure doesn't block another file in the same selection", async () => {
    mswServer.use(
      http.post("/api/v1/documents/presign", () =>
        HttpResponse.json(
          { error: { code: "quota_exceeded", message: "..." } },
          { status: 402 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithQueryClient(<UploadDialog open onOpenChange={() => {}} />);

    const fileA = new File(["a"], "a.pdf", { type: "application/pdf" });
    const fileB = new File(["b"], "b.pdf", { type: "application/pdf" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, [fileA, fileB]);

    expect(await screen.findAllByText(/storage quota/i)).toHaveLength(2);
    expect(screen.getByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("b.pdf")).toBeInTheDocument();
  });
});
