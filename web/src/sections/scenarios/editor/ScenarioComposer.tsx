"use client";

import { useMemo, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  InputSelect,
  InputTextArea,
  InputTypeIn,
  MessageCard,
  Tag,
  Text,
  Tooltip,
} from "@opal/components";
import { Content, InputVertical } from "@opal/layouts";
import {
  SvgArrowLeft,
  SvgBlocks,
  SvgPlayCircle,
  SvgPlus,
  SvgShare,
  SvgSimpleLoader,
  SvgTrash,
} from "@opal/icons";
import {
  BUILTIN_SCENARIO_DOMAINS,
  isBuiltinScenarioDomain,
  isUncategorizedDomain,
  normalizeScenarioDomain,
  playbookToRules,
  renderScenarioProtocolPreview,
  scenarioDomainMessageKey,
} from "@/lib/scenarios/types";
import {
  SYSTEM_CATALOG_CATEGORIES,
  categoryMessageKey,
  type SystemCatalogCategory,
} from "@/lib/system-catalog/types";
import ConditionalRules from "@/sections/scenarios/editor/ConditionalRules";
import PlaybookInspector from "@/sections/scenarios/editor/PlaybookInspector";
import ScenarioPreview from "@/sections/scenarios/editor/ScenarioPreview";
import SkillPipeline from "@/sections/scenarios/editor/SkillPipeline";
import type {
  ConditionalDraft,
  ScenarioDraft,
  ScenarioEditorMode,
  SkillOption,
  TemplateOption,
} from "@/sections/scenarios/editor/types";
import { conditionalsToRules } from "@/sections/scenarios/editor/types";

const NONE_TEMPLATE_VALUE = "__none__";
const DOMAIN_NAME_MAX = 64;

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
  const [domainQuery, setDomainQuery] = useState("");
  const [templateQuery, setTemplateQuery] = useState("");
  const [tagDraft, setTagDraft] = useState("");
  const [createdDomains, setCreatedDomains] = useState<string[]>([]);

  const skillByKey = useMemo(() => {
    const map = new Map<string, SkillOption>();
    for (const skill of skillCatalog) {
      map.set(skill.key, skill);
    }
    return map;
  }, [skillCatalog]);

  const preview = renderScenarioProtocolPreview({
    name: draft.name.trim(),
    description: draft.description.trim(),
    skillNames: draft.skillKeys.map(
      (key) => skillByKey.get(key)?.name ?? key
    ),
    reportTemplate: draft.reportTemplate.trim() || null,
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

  const customDomains = useMemo(() => {
    const names = new Set(knownCustomDomains);
    for (const extra of createdDomains) {
      names.add(extra);
    }
    if (!isBuiltinScenarioDomain(draft.domain) && !isUncategorizedDomain(draft.domain)) {
      names.add(draft.domain);
    }
    return Array.from(names).sort((left, right) => left.localeCompare(right));
  }, [createdDomains, draft.domain, knownCustomDomains]);

  const visibleCustomDomains = useMemo(() => {
    const query = domainQuery.trim().toLowerCase();
    if (!query) return customDomains;
    return customDomains.filter((item) => item.toLowerCase().includes(query));
  }, [customDomains, domainQuery]);

  const domainCreateName = domainQuery.trim().slice(0, DOMAIN_NAME_MAX);
  const canCreateDomain =
    domainCreateName.length > 0 &&
    !isBuiltinScenarioDomain(domainCreateName) &&
    !isUncategorizedDomain(domainCreateName) &&
    !customDomains.some(
      (item) => item.toLowerCase() === domainCreateName.toLowerCase()
    );

  const selectedCustomDomain =
    !isBuiltinScenarioDomain(draft.domain) && !isUncategorizedDomain(draft.domain)
      ? draft.domain
      : undefined;

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
      draft.reportTemplate &&
      !rows.some((item) => item.slug === draft.reportTemplate) &&
      (!query || draft.reportTemplate.toLowerCase().includes(query))
    ) {
      return [
        ...rows,
        { slug: draft.reportTemplate, name: draft.reportTemplate },
      ];
    }
    return rows;
  }, [draft.reportTemplate, templateQuery, templates]);

  function selectDomain(next: string) {
    const normalized = normalizeScenarioDomain(next);
    if (
      !isBuiltinScenarioDomain(normalized) &&
      !isUncategorizedDomain(normalized)
    ) {
      setCreatedDomains((current) =>
        current.includes(normalized) ? current : [...current, normalized]
      );
    }
    onDraftChange({ domain: normalized });
    setDomainQuery("");
  }

  function addTag(raw: string) {
    const tag = raw.trim().toLowerCase();
    if (!tag || draft.tags.includes(tag)) return;
    onDraftChange({ tags: [...draft.tags, tag] });
    setTagDraft("");
  }

  const headerTitle = isCreating
    ? t("header.title.create")
    : draft.name.trim() || t("header.title.edit");

  const nameOk = draft.name.trim().length > 0;
  const skillsOk = draft.skillKeys.length >= 1;
  const slugOk =
    mode !== "catalog" || !isCreating || draft.slug.trim().length > 0;

  function scrollToPreview() {
    document
      .getElementById("scenario-preview")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div
      className="flex h-full min-h-0 w-full flex-col bg-background-neutral-00"
      data-testid="ScenarioComposer/container"
    >
      <header className="flex shrink-0 flex-col gap-2 border-b border-border-01 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              size="sm"
              prominence="tertiary"
              icon={SvgArrowLeft}
              aria-label={t("header.back.ariaLabel")}
              disabled={saving}
              onClick={onCancel}
            />
            <SvgBlocks className="shrink-0 text-text-03" />
            <Text font="heading-h3" as="h1" nowrap>
              {headerTitle}
            </Text>
            {isDirty && (
              <Tag size="sm" color="amber" title={t("header.dirty.label")} />
            )}
            {statusTags}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              size="sm"
              prominence="tertiary"
              type="button"
              onClick={scrollToPreview}
            >
              {t("header.preview.label")}
            </Button>
            <Button
              size="sm"
              prominence="secondary"
              type="button"
              disabled={saving}
              onClick={onCancel}
            >
              {t("header.cancel.label")}
            </Button>
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
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!isCreating && isLoading && (
          <div className="flex justify-center p-6">
            <SvgSimpleLoader />
          </div>
        )}

        {!isCreating && error && !isLoading && (
          <div className="p-4">
            <MessageCard
              variant="error"
              title={t("error.title")}
              description={t("error.description")}
            />
          </div>
        )}

        {(isCreating || (!isLoading && !error)) && (
          <div className="grid min-h-full grid-cols-1 gap-0 lg:grid-cols-[minmax(0,1.15fr)_minmax(22rem,0.85fr)]">
            <section className="flex min-h-0 flex-col gap-4 border-border-01 p-4 lg:border-e">
              {!canEdit && (
                <MessageCard
                  variant="info"
                  title={t("status.viewer.title")}
                  description={t("status.viewer.description")}
                />
              )}
              <SkillPipeline
                skillKeys={draft.skillKeys}
                skillCatalog={skillCatalog}
                fieldsLocked={fieldsLocked}
                onChange={(skillKeys) => onDraftChange({ skillKeys })}
              />
              <ConditionalRules
                conditionals={conditionals}
                skillCatalog={skillCatalog}
                fieldsLocked={fieldsLocked}
                onChange={onConditionalsChange}
              />
            </section>

            <aside className="flex flex-col gap-4 bg-background-tint-00 p-4">
              <InputVertical withLabel="scenario-name" title={t("identity.name.title")}>
                <InputTypeIn
                  id="scenario-name"
                  value={draft.name}
                  maxLength={128}
                  placeholder={t("identity.name.placeholder")}
                  variant={fieldsLocked ? "disabled" : "primary"}
                  onChange={(event) => onDraftChange({ name: event.target.value })}
                />
              </InputVertical>

              {mode === "catalog" && (
                <InputVertical withLabel="scenario-slug" title={t("identity.slug.title")}>
                  <InputTypeIn
                    id="scenario-slug"
                    value={draft.slug}
                    maxLength={64}
                    placeholder={t("identity.slug.placeholder")}
                    variant={
                      fieldsLocked || !isCreating ? "disabled" : "primary"
                    }
                    onChange={(event) =>
                      onDraftChange({ slug: event.target.value })
                    }
                  />
                </InputVertical>
              )}

              <InputVertical
                withLabel="scenario-description"
                title={t("identity.description.title")}
              >
                <InputTextArea
                  id="scenario-description"
                  rows={3}
                  value={draft.description}
                  placeholder={t("identity.description.placeholder")}
                  autoResize
                  maxRows={6}
                  variant={fieldsLocked ? "disabled" : "primary"}
                  onChange={(event) =>
                    onDraftChange({ description: event.target.value })
                  }
                />
              </InputVertical>

              {mode === "user" ? (
                <InputVertical title={t("identity.domain.title")}>
                  <div className="flex flex-col gap-2">
                    <div className="flex flex-wrap gap-1">
                      {BUILTIN_SCENARIO_DOMAINS.map((item) => (
                        <Button
                          key={item}
                          size="sm"
                          type="button"
                          prominence={
                            draft.domain === item ? "primary" : "secondary"
                          }
                          disabled={fieldsLocked}
                          onClick={() => selectDomain(item)}
                        >
                          {tScenarios(scenarioDomainMessageKey(item))}
                        </Button>
                      ))}
                    </div>
                    <InputSelect
                      value={selectedCustomDomain}
                      disabled={fieldsLocked}
                      onValueChange={selectDomain}
                      onOpenChange={(open) => {
                        if (open) setDomainQuery("");
                      }}
                    >
                      <InputSelect.Trigger
                        placeholder={t("identity.domain.placeholder")}
                      />
                      <InputSelect.Content>
                        <InputSelect.Search
                          value={domainQuery}
                          onChange={(event) =>
                            setDomainQuery(
                              event.target.value.slice(0, DOMAIN_NAME_MAX)
                            )
                          }
                          placeholder={t("identity.domain.search.placeholder")}
                        />
                        {visibleCustomDomains.map((item) => (
                          <InputSelect.Item key={item} value={item}>
                            {item}
                          </InputSelect.Item>
                        ))}
                        {canCreateDomain ? (
                          <InputSelect.Item value={domainCreateName}>
                            {t("identity.domain.create.label", {
                              name: domainCreateName,
                            })}
                          </InputSelect.Item>
                        ) : null}
                        {visibleCustomDomains.length === 0 && !canCreateDomain ? (
                          <div className="px-2 py-1.5">
                            <Text color="text-03">
                              {t("identity.domain.empty.text")}
                            </Text>
                          </div>
                        ) : null}
                      </InputSelect.Content>
                    </InputSelect>
                  </div>
                </InputVertical>
              ) : (
                <div className="flex flex-col gap-3">
                  <InputVertical title={t("identity.category.title")}>
                    <InputSelect
                      value={draft.category}
                      disabled={fieldsLocked}
                      onValueChange={(value) =>
                        onDraftChange({
                          category: value as SystemCatalogCategory,
                        })
                      }
                    >
                      <InputSelect.Trigger
                        placeholder={t("identity.category.title")}
                      />
                      <InputSelect.Content>
                        {SYSTEM_CATALOG_CATEGORIES.map((value) => (
                          <InputSelect.Item key={value} value={value}>
                            {tGallery(categoryMessageKey(value))}
                          </InputSelect.Item>
                        ))}
                      </InputSelect.Content>
                    </InputSelect>
                  </InputVertical>
                  <InputVertical title={t("identity.tags.title")}>
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap gap-1">
                        {draft.tags.map((tag) => (
                          <div key={tag} className="flex items-center gap-1">
                            <Tag size="sm" color="gray" title={tag} />
                            <Button
                              size="xs"
                              prominence="tertiary"
                              icon={SvgTrash}
                              disabled={fieldsLocked}
                              aria-label={t("identity.tags.remove.ariaLabel", {
                                tag,
                              })}
                              onClick={() =>
                                onDraftChange({
                                  tags: draft.tags.filter((item) => item !== tag),
                                })
                              }
                            />
                          </div>
                        ))}
                      </div>
                      <InputTypeIn
                        value={tagDraft}
                        placeholder={t("identity.tags.placeholder")}
                        variant={fieldsLocked ? "disabled" : "primary"}
                        onChange={(event) => setTagDraft(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            addTag(tagDraft);
                          }
                        }}
                      />
                      <Button
                        size="sm"
                        prominence="tertiary"
                        icon={SvgPlus}
                        disabled={fieldsLocked || !tagDraft.trim()}
                        onClick={() => addTag(tagDraft)}
                      >
                        {t("identity.tags.add.label")}
                      </Button>
                    </div>
                  </InputVertical>
                </div>
              )}

              <InputVertical title={t("template.title")}>
                <InputSelect
                  value={draft.reportTemplate || NONE_TEMPLATE_VALUE}
                  disabled={fieldsLocked}
                  onValueChange={(value) =>
                    onDraftChange({
                      reportTemplate:
                        value === NONE_TEMPLATE_VALUE ? "" : value,
                    })
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

              <PlaybookInspector
                playbook={draft.playbook}
                playbookDomain={draft.domain}
                showDomainField={mode === "catalog"}
                fieldsLocked={fieldsLocked}
                onPlaybookChange={(playbook) => onDraftChange({ playbook })}
                onDomainChange={(domain) => onDraftChange({ domain })}
              />

              <div
                className="flex flex-col gap-2"
                data-testid="ScenarioComposer/validation"
              >
                <Content
                  title={t("validation.checklist.title")}
                  sizePreset="main-content"
                  variant="section"
                />
                <div className="flex flex-col gap-1">
                  <Tag
                    size="sm"
                    color={nameOk ? "green" : "gray"}
                    title={
                      nameOk ? t("validation.ready.name") : t("validation.name")
                    }
                  />
                  <Tag
                    size="sm"
                    color={skillsOk ? "green" : "gray"}
                    title={
                      skillsOk
                        ? t("validation.ready.skills")
                        : t("validation.skills")
                    }
                  />
                  {mode === "catalog" && isCreating && (
                    <Tag
                      size="sm"
                      color={slugOk ? "green" : "gray"}
                      title={
                        slugOk
                          ? t("validation.ready.slug")
                          : t("validation.slug")
                      }
                    />
                  )}
                </div>
              </div>

              <ScenarioPreview markdown={preview} />
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
