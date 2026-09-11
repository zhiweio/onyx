"use client";

import { useTranslations } from "next-intl";
import { Button, InputSelect, InputTypeIn } from "@opal/components";
import { Content } from "@opal/layouts";
import { SvgPlus, SvgTrash } from "@opal/icons";
import type {
  ConditionalDraft,
  SkillOption,
} from "@/sections/scenarios/editor/types";
import { emptyConditionalDraft } from "@/sections/scenarios/editor/types";

interface ConditionalRulesProps {
  conditionals: ConditionalDraft[];
  skillCatalog: SkillOption[];
  fieldsLocked: boolean;
  onChange: (conditionals: ConditionalDraft[]) => void;
}

export default function ConditionalRules({
  conditionals,
  skillCatalog,
  fieldsLocked,
  onChange,
}: ConditionalRulesProps) {
  const t = useTranslations("craft.scenarioEditor");

  function updateAt(index: number, patch: Partial<ConditionalDraft>) {
    onChange(
      conditionals.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item
      )
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Content
          title={t("conditional.title")}
          sizePreset="main-content"
          variant="section"
        />
        <Button
          size="sm"
          prominence="tertiary"
          icon={SvgPlus}
          disabled={fieldsLocked}
          onClick={() => onChange([...conditionals, emptyConditionalDraft()])}
        >
          {t("conditional.add.label")}
        </Button>
      </div>
      {conditionals.length === 0 ? (
        <div className="rounded-08 border border-border-01 px-3 py-2">
          <Content
            title={t("conditional.empty.text")}
            sizePreset="secondary"
            variant="body"
            color="muted"
          />
        </div>
      ) : (
        conditionals.map((draft, index) => (
          <div
            key={`${index}-${draft.skillKey}`}
            className="grid grid-cols-1 items-center gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
          >
            <InputTypeIn
              value={draft.keywords}
              placeholder={t("conditional.keywords.placeholder")}
              variant={fieldsLocked ? "disabled" : "primary"}
              onChange={(event) =>
                updateAt(index, { keywords: event.target.value })
              }
            />
            <InputTypeIn
              value={draft.intent}
              placeholder={t("conditional.intent.placeholder")}
              variant={fieldsLocked ? "disabled" : "primary"}
              onChange={(event) =>
                updateAt(index, { intent: event.target.value })
              }
            />
            <InputSelect
              value={draft.skillKey || undefined}
              disabled={fieldsLocked}
              onValueChange={(value) => updateAt(index, { skillKey: value })}
            >
              <InputSelect.Trigger
                placeholder={t("conditional.skill.placeholder")}
              />
              <InputSelect.Content>
                {skillCatalog.map((skill) => (
                  <InputSelect.Item key={skill.key} value={skill.key}>
                    {skill.name}
                  </InputSelect.Item>
                ))}
              </InputSelect.Content>
            </InputSelect>
            <Button
              size="sm"
              prominence="tertiary"
              icon={SvgTrash}
              disabled={fieldsLocked}
              aria-label={t("conditional.remove.ariaLabel")}
              onClick={() =>
                onChange(
                  conditionals.filter((_, itemIndex) => itemIndex !== index)
                )
              }
            />
          </div>
        ))
      )}
    </div>
  );
}
