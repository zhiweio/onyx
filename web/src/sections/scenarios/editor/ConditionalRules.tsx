"use client";

import { useTranslations } from "next-intl";
import { Button, InputSelect, InputTypeIn, Text } from "@opal/components";
import { SvgPlus, SvgTrash } from "@opal/icons";
import EditorSection from "@/sections/scenarios/editor/EditorSection";
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
    <EditorSection
      title={t("sections.conditional.title")}
      description={t("sections.conditional.description")}
      action={
        <Button
          size="sm"
          prominence="secondary"
          icon={SvgPlus}
          disabled={fieldsLocked}
          onClick={() => onChange([...conditionals, emptyConditionalDraft()])}
        >
          {t("conditional.add.label")}
        </Button>
      }
    >
      {conditionals.length === 0 ? (
        <div className="rounded-08 border border-dashed border-border-02 px-3 py-3">
          <Text color="text-03">{t("conditional.empty.text")}</Text>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {conditionals.map((draft, index) => (
            <div
              key={`${index}-${draft.skillKey}`}
              className="flex flex-col gap-2 rounded-08 border border-border-01 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Text font="secondary-body" color="text-03">
                  {t("conditional.rule.if")}
                </Text>
                <div className="min-w-40 flex-1">
                  <InputTypeIn
                    value={draft.keywords}
                    placeholder={t("conditional.keywords.placeholder")}
                    variant={fieldsLocked ? "disabled" : "primary"}
                    onChange={(event) =>
                      updateAt(index, { keywords: event.target.value })
                    }
                  />
                </div>
                <Text font="secondary-body" color="text-03">
                  {t("conditional.rule.or")}
                </Text>
                <div className="min-w-36 flex-1">
                  <InputTypeIn
                    value={draft.intent}
                    placeholder={t("conditional.intent.placeholder")}
                    variant={fieldsLocked ? "disabled" : "primary"}
                    onChange={(event) =>
                      updateAt(index, { intent: event.target.value })
                    }
                  />
                </div>
                <Text font="secondary-body" color="text-03">
                  {t("conditional.rule.add")}
                </Text>
                <div className="min-w-44 flex-1">
                  <InputSelect
                    value={draft.skillKey || undefined}
                    disabled={fieldsLocked}
                    onValueChange={(value) =>
                      updateAt(index, { skillKey: value })
                    }
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
                </div>
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
            </div>
          ))}
        </div>
      )}
    </EditorSection>
  );
}
