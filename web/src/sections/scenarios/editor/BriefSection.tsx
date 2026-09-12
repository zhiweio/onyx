"use client";

import { useTranslations } from "next-intl";
import { InputTextArea } from "@opal/components";
import { InputVertical } from "@opal/layouts";
import type { ScenarioPlaybookDraft } from "@/lib/scenarios/types";
import EditorSection from "@/sections/scenarios/editor/EditorSection";
import StringListEditor from "@/sections/scenarios/editor/StringListEditor";

interface BriefSectionProps {
  playbook: ScenarioPlaybookDraft;
  fieldsLocked: boolean;
  onPlaybookChange: (playbook: ScenarioPlaybookDraft) => void;
}

export default function BriefSection({
  playbook,
  fieldsLocked,
  onPlaybookChange,
}: BriefSectionProps) {
  const t = useTranslations("craft.scenarioEditor");

  return (
    <EditorSection
      title={t("sections.brief.title")}
      description={t("sections.brief.description")}
    >
      <InputVertical
        withLabel="playbook-objective"
        title={t("playbook.objective.title")}
      >
        <InputTextArea
          id="playbook-objective"
          rows={5}
          value={playbook.objective}
          placeholder={t("playbook.objective.placeholder")}
          autoResize
          maxRows={12}
          variant={fieldsLocked ? "disabled" : "primary"}
          onChange={(event) =>
            onPlaybookChange({ ...playbook, objective: event.target.value })
          }
        />
      </InputVertical>
      <InputVertical title={t("playbook.inputs.title")}>
        <StringListEditor
          values={playbook.required_inputs}
          placeholder={t("playbook.inputs.placeholder")}
          addLabel={t("playbook.inputs.add.label")}
          removeAriaLabel={t("playbook.remove.ariaLabel")}
          disabled={fieldsLocked}
          onChange={(required_inputs) =>
            onPlaybookChange({ ...playbook, required_inputs })
          }
        />
      </InputVertical>
    </EditorSection>
  );
}
