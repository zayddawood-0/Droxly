import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Composer } from "./composer";

describe("Composer — ui-ux.md §8", () => {
  it("sends on Enter and clears the input", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer onSend={onSend} onStop={vi.fn()} isStreaming={false} />);

    const textarea = screen.getByLabelText("Message");
    await user.type(textarea, "What is the revenue?");
    await user.keyboard("{Enter}");

    expect(onSend).toHaveBeenCalledWith("What is the revenue?");
    expect(textarea).toHaveValue("");
  });

  it("inserts a newline on Shift+Enter instead of sending", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer onSend={onSend} onStop={vi.fn()} isStreaming={false} />);

    const textarea = screen.getByLabelText("Message");
    await user.type(textarea, "line one");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(textarea, "line two");

    expect(onSend).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("line one\nline two");
  });

  it("never sends an empty or whitespace-only message", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer onSend={onSend} onStop={vi.fn()} isStreaming={false} />);

    await user.type(screen.getByLabelText("Message"), "   ");
    await user.keyboard("{Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("shows a Stop control instead of Send while streaming", async () => {
    const onStop = vi.fn();
    const user = userEvent.setup();
    render(<Composer onSend={vi.fn()} onStop={onStop} isStreaming />);

    expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop generating" }));
    expect(onStop).toHaveBeenCalledOnce();
  });

  it("documents the Enter/Shift+Enter convention visibly", () => {
    render(<Composer onSend={vi.fn()} onStop={vi.fn()} isStreaming={false} />);
    expect(screen.getByText(/enter to send/i)).toBeInTheDocument();
  });
});
