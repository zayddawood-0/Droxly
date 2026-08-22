"use client";

import { useState } from "react";
import { Send, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

/**
 * ui-ux.md §8 — textarea + send + stop; "Enter-to-send / Shift+Enter-for-
 * newline documented via a visible hint" (NFR-A11Y-001); fixed to the
 * viewport bottom (handled by the parent's sticky positioning), above the
 * mobile keyboard.
 */
export function Composer({
  onSend,
  onStop,
  isStreaming,
  disabled,
}: {
  onSend: (content: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <div className="flex flex-col gap-1.5 border-t border-border bg-background p-3">
      <div className="flex items-end gap-2">
        <Textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder="Ask a question about your documents…"
          aria-label="Message"
          disabled={disabled}
          rows={1}
          className="max-h-40 min-h-10 flex-1 resize-none"
        />
        {isStreaming ? (
          <Button type="button" variant="outline" size="icon" onClick={onStop} aria-label="Stop generating">
            <Square className="size-4" aria-hidden="true" />
          </Button>
        ) : (
          <Button
            type="button"
            size="icon"
            onClick={submit}
            disabled={!value.trim() || disabled}
            aria-label="Send message"
          >
            <Send className="size-4" aria-hidden="true" />
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">Enter to send · Shift+Enter for a new line</p>
    </div>
  );
}
