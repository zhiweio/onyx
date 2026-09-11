"use client";

import { useTranslations } from "next-intl";
import { Card } from "@opal/components";
import { Content } from "@opal/layouts";

interface ScenarioPreviewProps {
  markdown: string;
}

export default function ScenarioPreview({ markdown }: ScenarioPreviewProps) {
  const t = useTranslations("craft.scenarioEditor");
  return (
    <div
      id="scenario-preview"
      className="flex flex-col gap-2"
      data-testid="ScenarioComposer/preview"
    >
      <Content
        title={t("preview.title")}
        sizePreset="main-content"
        variant="section"
      />
      <Card border="solid" rounding={4} padding={3} background="heavy">
        <pre className="m-0 max-h-64 overflow-y-auto whitespace-pre-wrap wrap-break-word font-mono text-xs leading-5 text-text-03">
          {markdown.trim() ? markdown : t("preview.empty.text")}
        </pre>
      </Card>
    </div>
  );
}
