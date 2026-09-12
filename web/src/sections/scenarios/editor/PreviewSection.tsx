"use client";

import { useTranslations } from "next-intl";
import { Card, Divider } from "@opal/components";

interface PreviewSectionProps {
  markdown: string;
}

export default function PreviewSection({ markdown }: PreviewSectionProps) {
  const t = useTranslations("craft.scenarioEditor");

  return (
    <div data-testid="ScenarioComposer/preview-toggle">
      <Divider
        foldable
        title={t("sections.preview.title")}
        defaultOpen={false}
      >
        <div
          id="scenario-preview"
          className="pt-2"
          data-testid="ScenarioComposer/preview"
        >
          <Card border="solid" rounding={4} padding={3} background="heavy">
            <pre className="m-0 max-h-64 overflow-y-auto whitespace-pre-wrap wrap-break-word font-mono text-xs leading-5 text-text-03">
              {markdown.trim() ? markdown : t("preview.empty.text")}
            </pre>
          </Card>
        </div>
      </Divider>
    </div>
  );
}
