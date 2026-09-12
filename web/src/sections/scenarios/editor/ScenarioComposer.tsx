"use client";

import { useMemo, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Divider,
  MessageCard,
  Tag,
  Tooltip,
} from "@opal/components";
import { SettingsLayouts } from "@opal/layouts";
import {
  SvgBlocks,
  SvgPlayCircle,
  SvgShare,
  SvgSimpleLoader,
} from "@opal/icons";
import {
  isBuiltinScenarioDomain,
  isUncategorizedDomain,
  playbookToRules,
  renderScenarioProtocolPreview,
  scenarioDomainMessageKey,
} from "@/lib/scenarios/types";
import { categoryMessageKey } from "@/lib/system-catalog/types";
import AdvancedPlaybook from "@/sections/scenarios/editor/AdvancedPlaybook";
import BriefSection from "@/sections/scenarios/editor/BriefSection";
import ConditionalRules from "@/sections/scenarios/editor/ConditionalRules";
import IdentitySection from "@/sections/scenarios/editor/IdentitySection";
import OutputSection from "@/sections/scenarios/editor/OutputSection";
import PreviewSection from "@/sections/scenarios/editor/PreviewSection";
import SkillPipeline from "@/sections/scenarios/editor/SkillPipeline";
import type {
  ConditionalDraft,
  ScenarioDraft,
  ScenarioEditorMode,
  SkillOption,
  TemplateOption,
} from "@/sections/scenarios/editor/types";
import { conditionalsToRules } from "@/sections/scenarios/editor/types";

interface ScenarioComposerProps {
  mode: ScenarioEditorMode;
  isCreating: boolean;
  isLoading: boolean;
  error: unknown;
  canEdit: boolean;
  fieldsLocked: boolean;
  draft: ScenarioDraft;
  conditionals: ConditionalDraft[];
  onDraftChange: (patch: Partial<ScenarioDraft>) => void;
  onConditionalsChange: (conditionals: ConditionalDraft[]) => void;
  skillCatalog: SkillOption[];
  templates: TemplateOption[];
  knownCustomDomains?: string[];
  statusTags?: ReactNode;
  isDirty?: boolean;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
  canSave: boolean;
  saveTooltip?: string;
  onShare?: () => void;
  onStartRun?: () => void;
  starting?: boolean;
  onCustomize?: () => void;
  customizing?: boolean;
  onPublish?: () => void;
  onUnpublish?: () => void;
}

export default function ScenarioComposer({
  mode,
  isCreating,
  isLoading,
  error,
  canEdit,
  fieldsLocked,
  draft,
  conditionals,
  onDraftChange,
  onConditionalsChange,
  skillCatalog,
  templates,
  knownCustomDomains = [],
  statusTags,
  isDirty = false,
  onCancel,
  onSave,
  saving,
  canSave,
  saveTooltip,
  onShare,
  onStartRun,
  starting = false,
  onCustomize,
  customizing = false,
  onPublish,
  onUnpublish,
}: ScenarioComposerProps) {
  const t = useTranslations("craft.scenarioEditor");
  const tScenarios = useTranslations("craft.scenarios");
  const tGallery = useTranslations("craft.gallery");

  const skillByKey = useMemo(() => {
    const map = new Map<string, SkillOption>();
    for (const skill of skillCatalog) {
      map.set(skill.key, skill);
    }
    return map;
  }, [skillCatalog]);

  const skillLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    for (const skill of skillCatalog) {
      labels[skill.key] = skill.name;
    }
    return labels;
  }, [skillCatalog]);

  const preview = renderScenarioProtocolPreview({
    name: draft.name.trim(),
    description: draft.description.trim(),
    skillNames: draft.skillKeys.map((key) => skillByKey.get(key)?.name ?? key),
    reportTemplate: draft.reportTemplate.trim() || null,
    skillLabels,
    rules: playbookToRules({
      domain: draft.domain,
      playbook: draft.playbook,
      extras: draft.extras,
      conditionals: conditionalsToRules(
        conditionals,
        mode === "catalog" ? "add_skill_slugs" : "add_skill_ids"
      ),
    }),
  });

  const headerTitle = isCreating
    ? t("header.title.create")
    : draft.name.trim() || t("header.title.edit");

  const recipeSummary = useMemo(() => {
    const domainLabel =
      mode === "catalog"
        ? tGallery(categoryMessageKey(draft.category))
        : isBuiltinScenarioDomain(draft.domain) ||
            isUncategorizedDomain(draft.domain)
          ? tScenarios(
              scenarioDomainMessageKey(
                isBuiltinScenarioDomain(draft.domain)
                  ? draft.domain
                  : "custom"
              )
            )
          : draft.domain;
    const templateLabel = draft.reportTemplate.trim()
      ? (templates.find((item) => item.slug === draft.reportTemplate)?.name ??
        draft.reportTemplate)
      : t("header.summary.noTemplate");
    const parts = [
      t("header.summary.skills", { count: draft.skillKeys.length }),
      domainLabel,
      templateLabel,
    ];
    if (conditionals.length > 0) {
      parts.push(
        t("header.summary.extras", { count: conditionals.length })
      );
    }
    return parts.join(" · ");
  }, [
    conditionals.length,
    draft.category,
    draft.domain,
    draft.reportTemplate,
    draft.skillKeys.length,
    mode,
    t,
    tGallery,
    tScenarios,
    templates,
  ]);

  const showForm = isCreating || (!isLoading && !error);

  return (
    <div className="h-full w-full" data-testid="ScenarioComposer/container">
      <SettingsLayouts.Root width="lg">
        <SettingsLayouts.Header
          icon={SvgBlocks}
          title={headerTitle}
          description={recipeSummary}
          backButton={onCancel}
          divider
          rightChildren={
            <div className="flex flex-wrap items-center justify-end gap-2">
              {mode === "user" && !isCreating && canEdit && onShare && (
                <Button
                  size="sm"
                  prominence="secondary"
                  type="button"
                  icon={SvgShare}
                  onClick={onShare}
                >
                  {t("header.share.label")}
                </Button>
              )}
              {mode === "user" && !isCreating && onStartRun && (
                <Button
                  size="sm"
                  prominence="secondary"
                  type="button"
                  icon={SvgPlayCircle}
                  disabled={starting}
                  onClick={onStartRun}
                >
                  {t("header.startRun.label")}
                </Button>
              )}
              {mode === "catalog" && !isCreating && onUnpublish && (
                <Button
                  size="sm"
                  prominence="secondary"
                  type="button"
                  disabled={saving}
                  onClick={onUnpublish}
                >
                  {t("header.unpublish.label")}
                </Button>
              )}
              {mode === "catalog" && !isCreating && onPublish && (
                <Button
                  size="sm"
                  prominence="secondary"
                  type="button"
                  disabled={saving}
                  onClick={onPublish}
                >
                  {t("header.publish.label")}
                </Button>
              )}
              <Button
                size="sm"
                prominence="secondary"
                type="button"
                disabled={saving}
                onClick={onCancel}
              >
                {t("header.cancel.label")}
              </Button>
              {canEdit ? (
                <Tooltip tooltip={saveTooltip} side="bottom">
                  <Button
                    size="sm"
                    type="button"
                    disabled={!canSave}
                    data-testid="ScenarioComposer/save"
                    onClick={onSave}
                  >
                    {saving ? t("header.saving.label") : t("header.save.label")}
                  </Button>
                </Tooltip>
              ) : (
                onCustomize && (
                  <Button
                    size="sm"
                    type="button"
                    disabled={customizing}
                    onClick={onCustomize}
                  >
                    {customizing
                      ? t("header.customizing.label")
                      : t("header.customize.label")}
                  </Button>
                )
              )}
            </div>
          }
        >
          {(isDirty || statusTags) && (
            <div className="flex flex-wrap items-center gap-2">
              {isDirty && (
                <Tag size="sm" color="amber" title={t("header.dirty.label")} />
              )}
              {statusTags}
            </div>
          )}
        </SettingsLayouts.Header>

        <SettingsLayouts.Body>
          {!isCreating && isLoading && (
            <div className="flex min-h-40 items-center justify-center">
              <SvgSimpleLoader />
            </div>
          )}

          {!isCreating && error && !isLoading && (
            <MessageCard
              variant="error"
              title={t("error.title")}
              description={t("error.description")}
            />
          )}

          {showForm && (
            <>
              {!canEdit && (
                <MessageCard
                  variant="info"
                  title={t("status.viewer.title")}
                  description={t("status.viewer.description")}
                />
              )}
              <IdentitySection
                mode={mode}
                isCreating={isCreating}
                fieldsLocked={fieldsLocked}
                draft={draft}
                knownCustomDomains={knownCustomDomains}
                onDraftChange={onDraftChange}
              />
              <Divider paddingParallel={0} paddingPerpendicular={0} />
              <BriefSection
                playbook={draft.playbook}
                fieldsLocked={fieldsLocked}
                onPlaybookChange={(playbook) => onDraftChange({ playbook })}
              />
              <Divider paddingParallel={0} paddingPerpendicular={0} />
              <SkillPipeline
                skillKeys={draft.skillKeys}
                skillCatalog={skillCatalog}
                fieldsLocked={fieldsLocked}
                onChange={(skillKeys) => onDraftChange({ skillKeys })}
              />
              <Divider paddingParallel={0} paddingPerpendicular={0} />
              <ConditionalRules
                conditionals={conditionals}
                skillCatalog={skillCatalog}
                fieldsLocked={fieldsLocked}
                onChange={onConditionalsChange}
              />
              <Divider paddingParallel={0} paddingPerpendicular={0} />
              <OutputSection
                reportTemplate={draft.reportTemplate}
                templates={templates}
                fieldsLocked={fieldsLocked}
                onChange={(reportTemplate) =>
                  onDraftChange({ reportTemplate })
                }
              />
              <Divider paddingParallel={0} paddingPerpendicular={0} />
              <AdvancedPlaybook
                playbook={draft.playbook}
                playbookDomain={draft.domain}
                showDomainField={mode === "catalog"}
                fieldsLocked={fieldsLocked}
                onPlaybookChange={(playbook) => onDraftChange({ playbook })}
                onDomainChange={(domain) => onDraftChange({ domain })}
              />
              <PreviewSection markdown={preview} />
            </>
          )}
        </SettingsLayouts.Body>
      </SettingsLayouts.Root>
    </div>
  );
}
