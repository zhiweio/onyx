"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { InputSelect, SelectCard, Text } from "@opal/components";
import { Content, InputVertical } from "@opal/layouts";
import EditorSection from "@/sections/scenarios/editor/EditorSection";
import type { TemplateOption } from "@/sections/scenarios/editor/types";

const NONE_TEMPLATE_VALUE = "__none__";

interface OutputSectionProps {
  reportTemplate: string;
  templates: TemplateOption[];
  fieldsLocked: boolean;
  onChange: (reportTemplate: string) => void;
}

export default function OutputSection({
  reportTemplate,
  templates,
  fieldsLocked,
  onChange,
}: OutputSectionProps) {
  const t = useTranslations("craft.scenarioEditor");
  const [templateQuery, setTemplateQuery] = useState("");

  const selected = templates.find((item) => item.slug === reportTemplate);
  const selectedFallback =
    reportTemplate && !selected
      ? { slug: reportTemplate, name: reportTemplate }
      : undefined;
  const current = selected ?? selectedFallback;

  const visibleTemplates = useMemo(() => {
    const query = templateQuery.trim().toLowerCase();
    const rows = templates.filter(
      (item) =>
        !query ||
        item.name.toLowerCase().includes(query) ||
        item.slug.toLowerCase().includes(query) ||
        (item.description ?? "").toLowerCase().includes(query)
    );
    if (
      current &&
      !rows.some((item) => item.slug === current.slug) &&
      (!query || current.slug.toLowerCase().includes(query))
    ) {
      return [...rows, current];
    }
    return rows;
  }, [current, templateQuery, templates]);

  return (
    <EditorSection
      title={t("sections.output.title")}
      description={t("sections.output.description")}
    >
      <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        <SelectCard
          state={reportTemplate ? "empty" : "selected"}
          padding={2}
          rounding={3}
          onClick={fieldsLocked ? undefined : () => onChange("")}
        >
          <Content
            sizePreset="main-ui"
            variant="section"
            title={t("template.none.title")}
            description={t("template.none.description")}
          />
        </SelectCard>
        {current ? (
          <SelectCard state="selected" padding={2} rounding={3}>
            <Content
              sizePreset="main-ui"
              variant="section"
              title={current.name}
              description={current.description || current.slug}
            />
          </SelectCard>
        ) : null}
      </div>
      <InputVertical title={t("template.choose.label")}>
        <InputSelect
          value={reportTemplate || NONE_TEMPLATE_VALUE}
          disabled={fieldsLocked}
          onValueChange={(value) =>
            onChange(value === NONE_TEMPLATE_VALUE ? "" : value)
          }
          onOpenChange={(open) => {
            if (open) setTemplateQuery("");
          }}
        >
          <InputSelect.Trigger placeholder={t("template.placeholder")} />
          <InputSelect.Content>
            <InputSelect.Search
              value={templateQuery}
              onChange={(event) => setTemplateQuery(event.target.value)}
              placeholder={t("template.search.placeholder")}
            />
            <InputSelect.Item value={NONE_TEMPLATE_VALUE}>
              {t("template.none.label")}
            </InputSelect.Item>
            {visibleTemplates.map((item) => (
              <InputSelect.Item key={item.slug} value={item.slug}>
                {item.name}
              </InputSelect.Item>
            ))}
            {visibleTemplates.length === 0 ? (
              <div className="px-2 py-1.5">
                <Text color="text-03">{t("template.empty.text")}</Text>
              </div>
            ) : null}
          </InputSelect.Content>
        </InputSelect>
      </InputVertical>
    </EditorSection>
  );
}
