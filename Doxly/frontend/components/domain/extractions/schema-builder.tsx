"use client";

import { Plus, Trash2 } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { FieldType, SchemaField } from "@/lib/api/extractions";

const FIELD_TYPES: { value: FieldType; label: string }[] = [
  { value: "string", label: "Text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "boolean", label: "Yes/No" },
];

/** ui-ux.md §10 — "custom SchemaBuilder (field name + type + required toggle, add/remove rows)"; starts with one blank row per the empty-state spec. */
export function SchemaBuilder({
  fields,
  onChange,
}: {
  fields: SchemaField[];
  onChange: (fields: SchemaField[]) => void;
}) {
  function updateField(index: number, patch: Partial<SchemaField>) {
    onChange(fields.map((field, i) => (i === index ? { ...field, ...patch } : field)));
  }

  function addRow() {
    onChange([...fields, { name: "", type: "string", required: false }]);
  }

  function removeRow(index: number) {
    onChange(fields.filter((_, i) => i !== index));
  }

  return (
    <div className="flex flex-col gap-2">
      {fields.map((field, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            value={field.name}
            onChange={(event) => updateField(index, { name: event.target.value })}
            placeholder="Field name"
            aria-label={`Field ${index + 1} name`}
            className="flex-1"
          />
          <Select
            value={field.type}
            onValueChange={(value) => updateField(index, { type: (value as FieldType) ?? "string" })}
          >
            <SelectTrigger className="w-28" aria-label={`Field ${index + 1} type`}>
              <SelectValue>
                {(value: FieldType) => FIELD_TYPES.find((t) => t.value === value)?.label ?? "Text"}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {FIELD_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground">
            <Checkbox
              checked={field.required}
              onCheckedChange={(checked) => updateField(index, { required: checked === true })}
              aria-label={`Field ${index + 1} required`}
            />
            Required
          </label>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() => removeRow(index)}
            disabled={fields.length === 1}
            aria-label={`Remove field ${index + 1}`}
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={addRow} className="self-start">
        <Plus className="size-4" aria-hidden="true" />
        Add field
      </Button>
    </div>
  );
}
