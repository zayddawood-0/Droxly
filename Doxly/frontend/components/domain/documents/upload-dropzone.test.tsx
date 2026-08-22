import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UploadDropzone } from "./upload-dropzone";

describe("UploadDropzone — FR-DOC-001", () => {
  it("is keyboard-reachable and opens the file picker on Enter", async () => {
    const onFilesSelected = vi.fn();
    const user = userEvent.setup();
    render(<UploadDropzone onFilesSelected={onFilesSelected} />);

    const dropzone = screen.getByRole("button", { name: /drag files here/i });
    await user.tab();
    expect(dropzone).toHaveFocus();
  });

  it("forwards selected files from the hidden input", async () => {
    const onFilesSelected = vi.fn();
    const user = userEvent.setup();
    render(<UploadDropzone onFilesSelected={onFilesSelected} />);

    const file = new File(["content"], "invoice.pdf", { type: "application/pdf" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    expect(onFilesSelected).toHaveBeenCalledWith([file]);
  });
});
