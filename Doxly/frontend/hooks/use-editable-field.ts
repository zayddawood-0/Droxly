import { useState } from "react";

/**
 * FR-EXT-004 — "editing a field value opens inline edit (not a separate
 * modal) and persists on blur/confirm" (ui-ux.md §10). Shared by both the
 * desktop table row and the mobile card rendering of the same field, so
 * the edit state machine has exactly one implementation.
 */
export function useEditableField(currentValue: unknown, onSave: (value: string) => Promise<void>) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  function startEdit() {
    setDraft(currentValue == null ? "" : String(currentValue));
    setEditing(true);
  }

  function cancel() {
    setEditing(false);
  }

  async function confirm() {
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      void confirm();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancel();
    }
  }

  return { editing, draft, setDraft, saving, startEdit, cancel, confirm, handleKeyDown };
}
