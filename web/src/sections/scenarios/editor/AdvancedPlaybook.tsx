"use client";

import { useTranslations } from "next-intl";
import { Button, Divider, InputTypeIn } from "@opal/components";
import { InputVertical } from "@opal/layouts";
import { SvgPlus, SvgTrash } from "@opal/icons";
import type { ScenarioPlaybookDraft } from "@/lib/scenarios/types";
import EditorSection from "@/sections/scenarios/editor/EditorSection";
import StringListEditor from "@/sections/scenarios/editor/StringListEditor";

interface AdvancedPlaybookProps {
  playbook: ScenarioPlaybookDraft;
  playbookDomain?: string;
  showDomainField?: boolean;
  fieldsLocked: boolean;
  onPlaybookChange: (playbook: ScenarioPlaybookDraft) => void;
  onDomainChange?: (domain: string) => void;
}

export default function AdvancedPlaybook({
  playbook,
  playbookDomain,
  showDomainField = false,
  fieldsLocked,
  onPlaybookChange,
  onDomainChange,
}: AdvancedPlaybookProps) {
  const t = useTranslations("craft.scenarioEditor");

  function patch(next: Partial<ScenarioPlaybookDraft>) {
    onPlaybookChange({ ...playbook, ...next });
  }

  const hasPhases = playbook.phases.some(
    (phase) => phase.id.trim() || (phase.done_when ?? "").trim()
  );

  return (
    <EditorSection
      title={t("sections.advanced.title")}
      description={t("sections.advanced.description")}
    >
      {showDomainField && (
        <InputVertical
          withLabel="playbook-domain"
          title={t("playbook.domain.title")}
        >
          <InputTypeIn
            id="playbook-domain"
            value={playbookDomain ?? ""}
            placeholder={t("playbook.domain.placeholder")}
            variant={fieldsLocked ? "disabled" : "primary"}
            onChange={(event) => onDomainChange?.(event.target.value)}
          />
        </InputVertical>
      )}

      <Divider
        foldable
        title={t("playbook.phases.fold", { count: playbook.phases.length })}
        defaultOpen={hasPhases}
      >
        <div className="flex flex-col gap-3 pt-2">
          {playbook.phases.map((phase, index) => (
            <div
              key={`${index}-${phase.id}`}
              className="flex flex-col gap-2 rounded-08 border border-border-01 p-3"
            >
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <InputVertical title={t("playbook.phases.id.title")}>
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
                  </InputVertical>
                </div>
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
              <InputVertical title={t("playbook.phases.doneWhen.title")}>
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
              </InputVertical>
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
      </Divider>

      <Divider
        foldable
        title={t("playbook.deliverables.fold", {
          count: playbook.deliverables.length,
        })}
        defaultOpen={playbook.deliverables.length > 0}
      >
        <div className="pt-2">
          <StringListEditor
            values={playbook.deliverables}
            placeholder={t("playbook.deliverables.placeholder")}
            addLabel={t("playbook.deliverables.add.label")}
            removeAriaLabel={t("playbook.remove.ariaLabel")}
            disabled={fieldsLocked}
            onChange={(deliverables) => patch({ deliverables })}
          />
        </div>
      </Divider>

      <Divider
        foldable
        title={t("playbook.gates.fold", {
          count: playbook.quality_gates.length,
        })}
        defaultOpen={playbook.quality_gates.length > 0}
      >
        <div className="pt-2">
          <StringListEditor
            values={playbook.quality_gates}
            placeholder={t("playbook.gates.placeholder")}
            addLabel={t("playbook.gates.add.label")}
            removeAriaLabel={t("playbook.remove.ariaLabel")}
            disabled={fieldsLocked}
            onChange={(quality_gates) => patch({ quality_gates })}
          />
        </div>
      </Divider>

      <Divider
        foldable
        title={t("playbook.refusals.fold", {
          count: playbook.refusal_rules.length,
        })}
        defaultOpen={playbook.refusal_rules.length > 0}
      >
        <div className="pt-2">
          <StringListEditor
            values={playbook.refusal_rules}
            placeholder={t("playbook.refusals.placeholder")}
            addLabel={t("playbook.refusals.add.label")}
            removeAriaLabel={t("playbook.remove.ariaLabel")}
            disabled={fieldsLocked}
            onChange={(refusal_rules) => patch({ refusal_rules })}
          />
        </div>
      </Divider>
    </EditorSection>
  );
}
