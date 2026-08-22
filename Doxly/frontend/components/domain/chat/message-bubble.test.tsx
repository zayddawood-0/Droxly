import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MessageBubble, type DisplayMessage } from "./message-bubble";

function makeMessage(overrides: Partial<DisplayMessage> = {}): DisplayMessage {
  return {
    id: "msg_1",
    role: "assistant",
    content: "Revenue grew twelve percent.",
    citations: [],
    status: "done",
    ...overrides,
  };
}

describe("MessageBubble — ui-ux.md §8", () => {
  it("renders a grounded assistant answer with its citations", () => {
    render(
      <MessageBubble
        message={makeMessage({
          citations: [{ document_id: "doc_1", page_number: 4, snippet: "...", relevance_score: 0.9 }],
        })}
      />,
    );

    expect(screen.getByText("Revenue grew twelve percent.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /citation 1: page 4/i })).toBeInTheDocument();
  });

  it("gives the zero-citation 'I don't know' response a visually distinct style (FR-AI-004)", () => {
    render(
      <MessageBubble
        message={makeMessage({ content: "Your documents don't contain information relevant to this question." })}
      />,
    );

    const bubble = screen.getByText(/don't contain information relevant/i);
    expect(bubble.className).toContain("border-dashed");
  });

  it("shows the streaming indicator only while a turn is still streaming", () => {
    const { rerender } = render(<MessageBubble message={makeMessage({ status: "streaming" })} />);
    expect(screen.getByRole("status", { name: /generating response/i })).toBeInTheDocument();

    rerender(<MessageBubble message={makeMessage({ status: "done" })} />);
    expect(screen.queryByRole("status", { name: /generating response/i })).not.toBeInTheDocument();
  });

  it("shows an inline error bubble with a Retry action, never a lost message", async () => {
    const onRetry = vi.fn();
    render(
      <MessageBubble
        message={makeMessage({ status: "error", content: "partial", errorMessage: "AI is taking longer than expected." })}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("partial");
    expect(screen.getByText("AI is taking longer than expected.")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows a stopped label when generation was stopped mid-turn", () => {
    render(<MessageBubble message={makeMessage({ status: "stopped" })} />);
    expect(screen.getByText("Generation stopped")).toBeInTheDocument();
  });

  it("only offers Regenerate on the last assistant message, and only when done", async () => {
    const onRegenerate = vi.fn();
    const { rerender } = render(
      <MessageBubble message={makeMessage()} isLastAssistantMessage onRegenerate={onRegenerate} />,
    );
    const button = screen.getByRole("button", { name: /regenerate/i });
    const user = userEvent.setup();
    await user.click(button);
    expect(onRegenerate).toHaveBeenCalledOnce();

    rerender(<MessageBubble message={makeMessage()} isLastAssistantMessage={false} onRegenerate={onRegenerate} />);
    expect(screen.queryByRole("button", { name: /regenerate/i })).not.toBeInTheDocument();
  });

  it("never shows citations or regenerate on a user message", () => {
    render(<MessageBubble message={makeMessage({ role: "user", content: "What is the revenue?" })} isLastAssistantMessage />);
    expect(screen.queryByRole("button", { name: /regenerate/i })).not.toBeInTheDocument();
  });
});
