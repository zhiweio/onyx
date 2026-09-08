"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { InputVertical } from "@opal/layouts";
import { InputTextArea } from "@opal/components";
import { Button } from "@opal/components";
import { SvgTrash } from "@opal/icons";
import { LongTermMemoryItem } from "@/lib/types";
import {
  createLongTermMemory,
  deleteLongTermMemory,
  listLongTermMemories,
  updateLongTermMemory,
} from "@/lib/long-term-memory/api";

export default function LongTermMemoryPanel() {
  const t = useTranslations("settings.memory");
  const [items, setItems] = useState<LongTermMemoryItem[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    const next = await listLongTermMemories();
    setItems(next);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <InputVertical
      title={t("longTerm.listTitle")}
      description={t("longTerm.listDescription")}
      withLabel
    >
      <div className="flex w-full flex-col gap-3">
        {items.map((item) => (
          <div key={item.id} className="flex w-full items-start gap-2">
            <InputTextArea
              value={item.text}
              rows={2}
              onChange={(event) => {
                const text = event.target.value;
                setItems((prev) =>
                  prev.map((row) =>
                    row.id === item.id ? { ...row, text } : row
                  )
                );
              }}
              onBlur={() => {
                void updateLongTermMemory(item.id, item.text);
              }}
            />
            <Button
              icon={SvgTrash}
              prominence="tertiary"
              size="sm"
              tooltip={t("longTerm.delete")}
              onClick={() => {
                void deleteLongTermMemory(item.id).then(() => refresh());
              }}
            />
          </div>
        ))}
        <InputTextArea
          value={draft}
          rows={2}
          placeholder={t("longTerm.addPlaceholder")}
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button
          prominence="secondary"
          size="sm"
          disabled={loading || draft.trim().length < 12}
          onClick={() => {
            setLoading(true);
            void createLongTermMemory(draft.trim())
              .then(() => {
                setDraft("");
                return refresh();
              })
              .finally(() => setLoading(false));
          }}
        >
          {t("longTerm.add")}
        </Button>
      </div>
    </InputVertical>
  );
}
