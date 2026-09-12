"use client";

import { Button, InputTypeIn } from "@opal/components";
import { SvgPlus, SvgTrash } from "@opal/icons";

interface StringListEditorProps {
  values: string[];
  placeholder: string;
  addLabel: string;
  removeAriaLabel: string;
  disabled?: boolean;
  onChange: (values: string[]) => void;
}

export default function StringListEditor({
  values,
  placeholder,
  addLabel,
  removeAriaLabel,
  disabled = false,
  onChange,
}: StringListEditorProps) {
  return (
    <div className="flex flex-col gap-2">
      {values.map((value, index) => (
        <div key={`${index}-${placeholder}`} className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <InputTypeIn
              value={value}
              placeholder={placeholder}
              variant={disabled ? "disabled" : "primary"}
              onChange={(event) => {
                const next = [...values];
                next[index] = event.target.value;
                onChange(next);
              }}
            />
          </div>
          <Button
            size="sm"
            prominence="tertiary"
            icon={SvgTrash}
            disabled={disabled}
            aria-label={removeAriaLabel}
            onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}
          />
        </div>
      ))}
      <Button
        size="sm"
        prominence="tertiary"
        icon={SvgPlus}
        disabled={disabled}
        onClick={() => onChange([...values, ""])}
      >
        {addLabel}
      </Button>
    </div>
  );
}
