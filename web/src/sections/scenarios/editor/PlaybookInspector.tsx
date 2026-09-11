"use client";

import { useTranslations } from "next-intl";
import { Button, InputTypeIn, InputTextArea } from "@opal/components";
import { Content, InputVertical } from "@opal/layouts";
import { SvgPlus, SvgTrash } from "@opal/icons";
import type { ScenarioPlaybookDraft } from "@/lib/scenarios/types";
import StringListEditor from "@/sections/scenarios/editor/StringListEditor";

interface PlaybookInspectorProps {
  playbook: ScenarioPlaybookDraft;
  playbookDomain?: string;
  showDomainField?: boolean;
  fieldsLocked: boolean;
  onPlaybookChange: (playbook: ScenarioPlaybookDraft) => void;
  onDomainChange?: (domain: string) => void;
}

export default function PlaybookInspector({
  playbook,
  playbookDomain,
  showDomainField = false,
  fieldsLocked,
  onPlaybookChange,
  onDomainChange,
}: PlaybookInspectorProps) {
  const t = useTranslations("craft.scenarioEditor");

  function patch(next: Partial<ScenarioPlaybookDraft>) {
    onPlaybookChange({ ...playbook, ...next });
  }

  return (
    <div className="flex flex-col gap-3">
      <Content
        title={t("playbook.title")}
        sizePreset="main-content"
        variant="section"
      />
      {showDomainField && (
        <InputVertical withLabel="playbook-domain" title={t("playbook.domain.title")}>
          <InputTypeIn
            id="playbook-domain"
            value={playbookDomain ?? ""}
            placeholder={t("playbook.domain.placeholder")}
            variant={fieldsLocked ? "disabled" : "primary"}
            onChange={(event) => onDomainChange?.(event.target.value)}
          />
        </InputVertical>
      )}
      <InputVertical withLabel="playbook-objective" title={t("playbook.objective.title")}>
        <InputTextArea
          id="playbook-objective"
          rows={3}
          value={playbook.objective}
          placeholder={t("playbook.objective.placeholder")}
          autoResize
          maxRows={8}
          variant={fieldsLocked ? "disabled" : "primary"}
          onChange={(event) => patch({ objective: event.target.value })}
        />
      </InputVertical>
      <InputVertical title={t("playbook.inputs.title")}>
        <StringListEditor
          values={playbook.required_inputs}
          placeholder={t("playbook.inputs.placeholder")}
          addLabel={t("playbook.inputs.add.label")}
          removeAriaLabel={t("playbook.remove.ariaLabel")}
          disabled={fieldsLocked}
          onChange={(required_inputs) => patch({ required_inputs })}
        />
      </InputVertical>
      <InputVertical title={t("playbook.phases.title")}>
        <div className="flex flex-col gap-2">
          {playbook.phases.map((phase, index) => (
            <div key={`${index}-${phase.id}`} className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <InputTypeIn
                  value={phase.id}
                  placeholder={t("playbook.phases.id.placeholder")}
                  variant={fieldsLocked ? "disabled" : "primary"}
                  onChange={(event) => {
                    const phases = playbook.phases.map((item, itemIndex) =>
                      itemIndex === index
                        ? { ...item, id: event.target.value }
                        : item
                    );
                    patch({ phases });
                  }}
                />
                <Button
                  size="sm"
                  prominence="tertiary"
                  icon={SvgTrash}
                  disabled={fieldsLocked}
                  aria-label={t("playbook.remove.ariaLabel")}
                  onClick={() =>
                    patch({
                      phases: playbook.phases.filter(
                        (_, itemIndex) => itemIndex !== index
                      ),
                    })
                  }
                />
              </div>
              <InputTypeIn
                value={phase.done_when ?? ""}
                placeholder={t("playbook.phases.doneWhen.placeholder")}
                variant={fieldsLocked ? "disabled" : "primary"}
                onChange={(event) => {
                  const phases = playbook.phases.map((item, itemIndex) =>
                    itemIndex === index
                      ? { ...item, done_when: event.target.value }
                      : item
                  );
                  patch({ phases });
                }}
              />
            </div>
          ))}
          <Button
            size="sm"
            prominence="tertiary"
            icon={SvgPlus}
            disabled={fieldsLocked}
            onClick={() =>
              patch({ phases: [...playbook.phases, { id: "", done_when: "" }] })
            }
          >
            {t("playbook.phases.add.label")}
          </Button>
        </div>
      </InputVertical>
      <InputVertical title={t("playbook.deliverables.title")}>
        <StringListEditor
          values={playbook.deliverables}
          placeholder={t("playbook.deliverables.placeholder")}
          addLabel={t("playbook.deliverables.add.label")}
          removeAriaLabel={t("playbook.remove.ariaLabel")}
          disabled={fieldsLocked}
          onChange={(deliverables) => patch({ deliverables })}
        />
      </InputVertical>
      <InputVertical title={t("playbook.gates.title")}>
        <StringListEditor
          values={playbook.quality_gates}
          placeholder={t("playbook.gates.placeholder")}
          addLabel={t("playbook.gates.add.label")}
          removeAriaLabel={t("playbook.remove.ariaLabel")}
          disabled={fieldsLocked}
          onChange={(quality_gates) => patch({ quality_gates })}
        />
      </InputVertical>
      <InputVertical title={t("playbook.refusals.title")}>
        <StringListEditor
          values={playbook.refusal_rules}
          placeholder={t("playbook.refusals.placeholder")}
          addLabel={t("playbook.refusals.add.label")}
          removeAriaLabel={t("playbook.remove.ariaLabel")}
          disabled={fieldsLocked}
          onChange={(refusal_rules) => patch({ refusal_rules })}
        />
      </InputVertical>
    </div>
  );
}
