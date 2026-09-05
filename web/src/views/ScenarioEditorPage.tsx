"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";
import {
  Button,
  Card,
  InputSelect,
  InputTextArea,
  InputTypeIn,
  MessageCard,
  Tag,
  Text,
  Tooltip,
} from "@opal/components";
import {
  Content,
  InputVertical,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import {
  SvgBlocks,
  SvgChevronDown,
  SvgChevronUp,
  SvgPlayCircle,
  SvgPlus,
  SvgShare,
  SvgSimpleLoader,
  SvgTrash,
} from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import useUnsavedChangesGuard from "@/hooks/useUnsavedChangesGuard";
import useUserSkills from "@/hooks/useUserSkills";
import useScenarios, { useScenario } from "@/hooks/useScenarios";
import { useReportTemplates } from "@/lib/report-templates/hooks";
import { SWR_KEYS } from "@/lib/swr-keys";
import {
  createScenario,
  duplicateScenario,
  updateScenario,
} from "@/lib/scenarios/api";
import { startScenarioRun } from "@/lib/scenarios/run";
import {
  BUILTIN_SCENARIO_DOMAINS,
  buildScenarioRules,
  canEditScenario,
  collectCustomScenarioDomains,
  isBuiltinScenarioDomain,
  isUncategorizedDomain,
  normalizeScenarioDomain,
  renderScenarioProtocolPreview,
  scenarioDomainMessageKey,
  type Scenario,
  type ScenarioConditionalRule,
} from "@/lib/scenarios/types";
import type { Skill } from "@/lib/skills/types";
import ShareScenarioModal from "@/sections/modals/scenarios/ShareScenarioModal";
import UnsavedChangesModal from "@/sections/modals/UnsavedChangesModal";
import {
  CRAFT_PATH,
  CRAFT_REPORT_TEMPLATES_PATH,
  CRAFT_SCENARIOS_PATH,
} from "@/app/craft/v1/constants";
import { CRAFT_SEARCH_PARAM_NAMES } from "@/app/craft/services/searchParams";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

const NONE_TEMPLATE_VALUE = "__none__";
const DOMAIN_NAME_MAX = 64;
const COMPOSER_PANE_CLASS =
  "flex min-h-96 flex-col gap-3 rounded-12 border border-border-01 bg-background-tint-00 p-3";
const COMPOSER_PANE_STYLE = {
  height: "min(32rem, calc(100vh - 18rem))",
} as const;

interface ConditionalDraft {
  keywords: string;
  intent: string;
  skillId: string;
}

interface ScenarioEditorPageProps {
  scenarioId?: string;
}

function skillsFromList(data: { builtins?: Skill[]; customs?: Skill[] } | undefined): Skill[] {
  return [...(data?.builtins ?? []), ...(data?.customs ?? [])];
}

function emptyConditional(): ConditionalDraft {
  return { keywords: "", intent: "", skillId: "" };
}

function parseConditionals(scenario: Scenario | undefined): ConditionalDraft[] {
  const rules = scenario?.rules?.conditional ?? [];
  return rules.map((rule) => ({
    keywords: (rule.if.query_contains_any ?? []).join(", "),
    intent: rule.if.intent ?? "",
    skillId: rule.add_skill_ids[0] ?? "",
  }));
}

function toConditionalRules(drafts: ConditionalDraft[]): ScenarioConditionalRule[] {
  return drafts.map((draft) => {
    const keywords = draft.keywords
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    return {
      if: {
        ...(keywords.length > 0 ? { query_contains_any: keywords } : {}),
        ...(draft.intent.trim() ? { intent: draft.intent.trim() } : {}),
      },
      add_skill_ids: draft.skillId ? [draft.skillId] : [],
    };
  });
}

function draftKey(input: {
  name: string;
  description: string;
  skillIds: string[];
  domain: string;
  reportTemplate: string;
  conditionals: ConditionalDraft[];
}): string {
  return JSON.stringify(input);
}

export default function ScenarioEditorPage({
  scenarioId,
}: ScenarioEditorPageProps) {
  const t = useTranslations("craft.scenarios");
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const isCreating = scenarioId === undefined;
  const { data: scenario, error, isLoading, refresh } = useScenario(scenarioId);
  const { data: allScenarios } = useScenarios();
  const { data: reportTemplates } = useReportTemplates();
  const { data: skillsData } = useUserSkills();
  const refreshSessionHistory = useBuildSessionStore(
    (state) => state.refreshSessionHistory
  );

  const allSkills = useMemo(() => skillsFromList(skillsData), [skillsData]);
  const skillById = useMemo(() => {
    const map = new Map<string, Skill>();
    for (const skill of allSkills) {
      map.set(skill.id, skill);
    }
    return map;
  }, [allSkills]);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [domain, setDomain] = useState("custom");
  const [reportTemplate, setReportTemplate] = useState("");
  const [conditionals, setConditionals] = useState<ConditionalDraft[]>([]);
  const [baseline, setBaseline] = useState("");
  const [hydratedId, setHydratedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [customizing, setCustomizing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [catalogQuery, setCatalogQuery] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [domainQuery, setDomainQuery] = useState("");
  const [createdDomains, setCreatedDomains] = useState<string[]>([]);
  const [templateQuery, setTemplateQuery] = useState("");

  useEffect(() => {
    if (isCreating && baseline === "") {
      setBaseline(
        draftKey({
          name: "",
          description: "",
          skillIds: [],
          domain: "custom",
          reportTemplate: "",
          conditionals: [],
        })
      );
    }
  }, [baseline, isCreating]);

  useEffect(() => {
    if (!scenario || scenario.id === hydratedId) return;
    const nextConditionals = parseConditionals(scenario);
    const nextName = scenario.name;
    const nextDescription = scenario.description;
    const nextSkillIds = scenario.skill_ids;
    const nextDomain = normalizeScenarioDomain(scenario.rules.domain);
    const nextTemplate = scenario.report_template ?? "";
    setName(nextName);
    setDescription(nextDescription);
    setSkillIds(nextSkillIds);
    setDomain(nextDomain);
    setReportTemplate(nextTemplate);
    setConditionals(nextConditionals);
    setBaseline(
      draftKey({
        name: nextName,
        description: nextDescription,
        skillIds: nextSkillIds,
        domain: nextDomain,
        reportTemplate: nextTemplate,
        conditionals: nextConditionals,
      })
    );
    setHydratedId(scenario.id);
  }, [hydratedId, scenario]);

  const currentDraft = draftKey({
    name,
    description,
    skillIds,
    domain,
    reportTemplate,
    conditionals,
  });
  const isDirty = baseline !== "" && currentDraft !== baseline;
  const unsavedChanges = useUnsavedChangesGuard({ isDirty });

  const canEdit = isCreating || (scenario ? canEditScenario(scenario) : false);
  const fieldsLocked = !canEdit || saving;
  const canSave =
    canEdit &&
    !saving &&
    isDirty &&
    name.trim().length > 0 &&
    skillIds.length >= 1;

  const knownCustomDomains = useMemo(() => {
    const names = new Set(collectCustomScenarioDomains(allScenarios));
    for (const extra of createdDomains) {
      names.add(extra);
    }
    if (!isBuiltinScenarioDomain(domain) && !isUncategorizedDomain(domain)) {
      names.add(domain);
    }
    return Array.from(names).sort((left, right) => left.localeCompare(right));
  }, [allScenarios, createdDomains, domain]);

  const visibleCustomDomains = useMemo(() => {
    const query = domainQuery.trim().toLowerCase();
    if (!query) return knownCustomDomains;
    return knownCustomDomains.filter((item) =>
      item.toLowerCase().includes(query)
    );
  }, [domainQuery, knownCustomDomains]);

  const domainCreateName = domainQuery.trim().slice(0, DOMAIN_NAME_MAX);
  const canCreateDomain =
    domainCreateName.length > 0 &&
    !isBuiltinScenarioDomain(domainCreateName) &&
    !isUncategorizedDomain(domainCreateName) &&
    !knownCustomDomains.some(
      (item) => item.toLowerCase() === domainCreateName.toLowerCase()
    );

  const selectedCustomDomain =
    !isBuiltinScenarioDomain(domain) && !isUncategorizedDomain(domain)
      ? domain
      : undefined;

  const visibleReportTemplates = useMemo(() => {
    const query = templateQuery.trim().toLowerCase();
    const rows = reportTemplates.filter(
      (item) =>
        !query ||
        item.name.toLowerCase().includes(query) ||
        item.slug.toLowerCase().includes(query) ||
        item.description.toLowerCase().includes(query)
    );
    if (
      reportTemplate &&
      !rows.some((item) => item.slug === reportTemplate) &&
      (!query || reportTemplate.toLowerCase().includes(query))
    ) {
      return [
        ...rows,
        {
          slug: reportTemplate,
          name: reportTemplate,
          description: "",
        },
      ];
    }
    return rows;
  }, [reportTemplate, reportTemplates, templateQuery]);

  const visibleCatalog = useMemo(() => {
    const query = catalogQuery.trim().toLowerCase();
    return allSkills.filter(
      (skill) =>
        !query ||
        skill.name.toLowerCase().includes(query) ||
        skill.description.toLowerCase().includes(query)
    );
  }, [allSkills, catalogQuery]);

  const traySkills: Array<{ id: string; name: string }> = skillIds.map(
    (id) => {
      const skill = skillById.get(id);
      return { id, name: skill?.name ?? id.slice(0, 8) };
    }
  );

  const preview = renderScenarioProtocolPreview({
    name: name.trim(),
    description: description.trim(),
    skillNames: skillIds.map((id) => skillById.get(id)?.name ?? id.slice(0, 8)),
    reportTemplate: reportTemplate.trim() || null,
  });

  const saveTooltip = !name.trim()
    ? t("editor.validation.name")
    : skillIds.length < 1
      ? t("editor.validation.skills")
      : undefined;

  function leaveEditor() {
    router.push(CRAFT_SCENARIOS_PATH as Route);
  }

  function handleCancel() {
    if (saving) return;
    unsavedChanges.requestLeave(leaveEditor);
  }

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
    setDomain(normalized);
    setDomainQuery("");
  }

  function addSkill(skillId: string) {
    if (fieldsLocked || skillIds.includes(skillId)) return;
    setSkillIds((current) => [...current, skillId]);
  }

  function removeSkill(skillId: string) {
    if (fieldsLocked) return;
    setSkillIds((current) => current.filter((id) => id !== skillId));
  }

  function moveSkill(skillId: string, delta: number) {
    if (fieldsLocked) return;
    setSkillIds((current) => {
      const index = current.indexOf(skillId);
      const nextIndex = index + delta;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.length) {
        return current;
      }
      const next = [...current];
      const item = next[index];
      if (item === undefined) return current;
      next.splice(index, 1);
      next.splice(nextIndex, 0, item);
      return next;
    });
  }

  async function refreshLists(saved: Scenario) {
    await mutate(SWR_KEYS.scenarios);
    await mutate(SWR_KEYS.scenario(saved.id), saved, { revalidate: false });
  }

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        skill_ids: skillIds,
        rules: buildScenarioRules({
          domain,
          conditionals: toConditionalRules(conditionals),
        }),
        report_template: reportTemplate.trim() || null,
      };
      const saved = isCreating || !scenarioId
        ? await createScenario(payload)
        : await updateScenario(scenarioId, payload);
      setBaseline(currentDraft);
      await refreshLists(saved);
      toast.success(
        isCreating ? t("toasts.created.message") : t("toasts.saved.message")
      );
      if (isCreating) {
        router.replace(`${CRAFT_SCENARIOS_PATH}/edit/${saved.id}` as Route);
      }
    } catch (saveError) {
      console.error(saveError);
      toast.error(
        saveError instanceof Error
          ? saveError.message
          : t("toasts.shareFailed.message")
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleCustomize() {
    if (!scenario || customizing) return;
    setCustomizing(true);
    try {
      const copied = await duplicateScenario(scenario.id);
      await refreshLists(copied);
      toast.success(t("toasts.duplicated.message"));
      router.replace(`${CRAFT_SCENARIOS_PATH}/edit/${copied.id}` as Route);
    } catch (customizeError) {
      console.error(customizeError);
      toast.error(
        customizeError instanceof Error
          ? customizeError.message
          : t("toasts.duplicateFailed.message")
      );
    } finally {
      setCustomizing(false);
    }
  }

  async function handleStart() {
    if (!scenario) return;
    setStarting(true);
    try {
      const sessionId = await startScenarioRun(scenario);
      await refreshSessionHistory();
      router.push(
        `${CRAFT_PATH}?${CRAFT_SEARCH_PARAM_NAMES.SESSION_ID}=${sessionId}` as Route
      );
    } catch (startError) {
      console.error(startError);
      toast.error(t("toasts.openFailed.message"));
    } finally {
      setStarting(false);
    }
  }

  const headerTitle = isCreating
    ? t("editor.title.create")
    : name.trim() || t("editor.title.edit");
  const headerDescription = isCreating
    ? t("editor.subtitle.create")
    : t("editor.subtitle.edit");

  return (
    <SettingsLayouts.Root
      width="lg"
      data-testid="ScenarioEditorPage/container"
    >
      <SettingsLayouts.Header
        icon={SvgBlocks}
        title={headerTitle}
        description={headerDescription}
        divider
        backButton={handleCancel}
        rightChildren={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              size="sm"
              prominence="secondary"
              type="button"
              disabled={saving}
              onClick={handleCancel}
            >
              {t("editor.cancel.label")}
            </Button>
            {!isCreating && canEdit && (
              <Button
                size="sm"
                prominence="secondary"
                type="button"
                icon={SvgShare}
                onClick={() => setShareOpen(true)}
              >
                {t("editor.share.label")}
              </Button>
            )}
            {!isCreating && scenario && (
              <Button
                size="sm"
                prominence="secondary"
                type="button"
                icon={SvgPlayCircle}
                disabled={starting}
                onClick={() => void handleStart()}
              >
                {t("editor.startRun.label")}
              </Button>
            )}
            {canEdit ? (
              <Tooltip tooltip={saveTooltip} side="bottom">
                <Button
                  size="sm"
                  type="button"
                  disabled={!canSave}
                  onClick={() => void handleSave()}
                >
                  {saving ? t("editor.saving.label") : t("editor.save.label")}
                </Button>
              </Tooltip>
            ) : (
              scenario && (
                <Button
                  size="sm"
                  type="button"
                  disabled={customizing}
                  onClick={() => void handleCustomize()}
                >
                  {customizing
                    ? t("editor.customizing.label")
                    : t("editor.customize.label")}
                </Button>
              )
            )}
          </div>
        }
      />

      <SettingsLayouts.Body>
        {!isCreating && isLoading && <SvgSimpleLoader />}

        {!isCreating && error && !isLoading && (
          <MessageCard
            variant="error"
            title={t("error.title")}
            description={t("error.description")}
          />
        )}

        {(isCreating || scenario) && !isLoading && !error && (
          <div className="flex flex-col gap-4">
            {!canEdit && (
              <MessageCard
                variant="info"
                title={t("card.access.viewer.label")}
                description={t("editor.readOnly.description")}
              />
            )}

            <Card border="solid" rounding={4} padding={3} background="light">
              <Section gap={3} alignItems="stretch">
                <Content
                  title={t("editor.identity.title")}
                  sizePreset="main-content"
                  variant="section"
                />
                <InputVertical
                  withLabel="pack-name"
                  title={t("editor.name.title")}
                >
                  <InputTypeIn
                    id="pack-name"
                    value={name}
                    maxLength={128}
                    onChange={(event) => setName(event.target.value)}
                    placeholder={t("editor.name.placeholder")}
                    variant={fieldsLocked ? "disabled" : "primary"}
                  />
                </InputVertical>
                <InputVertical
                  withLabel="pack-domain"
                  title={t("editor.domain.title")}
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex flex-wrap gap-1">
                      {BUILTIN_SCENARIO_DOMAINS.map((item) => (
                        <Button
                          key={item}
                          size="sm"
                          type="button"
                          prominence={
                            domain === item ? "primary" : "secondary"
                          }
                          disabled={fieldsLocked}
                          onClick={() => selectDomain(item)}
                        >
                          {t(scenarioDomainMessageKey(item))}
                        </Button>
                      ))}
                    </div>
                    <InputSelect
                      value={selectedCustomDomain}
                      onValueChange={selectDomain}
                      disabled={fieldsLocked}
                      onOpenChange={(open) => {
                        if (open) setDomainQuery("");
                      }}
                    >
                      <InputSelect.Trigger
                        placeholder={t("editor.domain.placeholder")}
                      />
                      <InputSelect.Content>
                        <InputSelect.Search
                          value={domainQuery}
                          onChange={(event) =>
                            setDomainQuery(
                              event.target.value.slice(0, DOMAIN_NAME_MAX)
                            )
                          }
                          placeholder={t("editor.domain.search.placeholder")}
                        />
                        {visibleCustomDomains.map((item) => (
                          <InputSelect.Item key={item} value={item}>
                            {item}
                          </InputSelect.Item>
                        ))}
                        {canCreateDomain ? (
                          <InputSelect.Item value={domainCreateName}>
                            {t("editor.domain.create.label", {
                              name: domainCreateName,
                            })}
                          </InputSelect.Item>
                        ) : null}
                        {visibleCustomDomains.length === 0 &&
                        !canCreateDomain ? (
                          <div className="px-2 py-1.5">
                            <Text color="text-03">
                              {t("editor.domain.empty.text")}
                            </Text>
                          </div>
                        ) : null}
                      </InputSelect.Content>
                    </InputSelect>
                  </div>
                </InputVertical>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(12rem,16rem)]">
                  <InputVertical
                    withLabel="pack-mission"
                    title={t("editor.description.title")}
                  >
                    <InputTextArea
                      id="pack-mission"
                      rows={2}
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                      placeholder={t("editor.description.placeholder")}
                      autoResize
                      maxRows={4}
                      variant={fieldsLocked ? "disabled" : "primary"}
                    />
                  </InputVertical>
                  <InputVertical
                    withLabel="pack-template"
                    title={t("editor.reportTemplate.title")}
                  >
                    <div className="flex flex-col gap-2">
                      <InputSelect
                        value={reportTemplate || NONE_TEMPLATE_VALUE}
                        onValueChange={(value) =>
                          setReportTemplate(
                            value === NONE_TEMPLATE_VALUE ? "" : value
                          )
                        }
                        disabled={fieldsLocked}
                        onOpenChange={(open) => {
                          if (open) setTemplateQuery("");
                        }}
                      >
                        <InputSelect.Trigger
                          placeholder={t(
                            "editor.reportTemplate.placeholder"
                          )}
                        />
                        <InputSelect.Content>
                          <InputSelect.Search
                            value={templateQuery}
                            onChange={(event) =>
                              setTemplateQuery(event.target.value)
                            }
                            placeholder={t(
                              "editor.reportTemplate.search.placeholder"
                            )}
                          />
                          <InputSelect.Item value={NONE_TEMPLATE_VALUE}>
                            {t("editor.reportTemplate.none.label")}
                          </InputSelect.Item>
                          {visibleReportTemplates.map((item) => (
                            <InputSelect.Item
                              key={item.slug}
                              value={item.slug}
                            >
                              {item.name}
                            </InputSelect.Item>
                          ))}
                          {visibleReportTemplates.length === 0 ? (
                            <div className="px-2 py-1.5">
                              <Text color="text-03">
                                {t("editor.reportTemplate.empty.text")}
                              </Text>
                            </div>
                          ) : null}
                        </InputSelect.Content>
                      </InputSelect>
                      <Button
                        prominence="tertiary"
                        size="sm"
                        type="button"
                        onClick={() =>
                          // SAFETY: CRAFT_REPORT_TEMPLATES_PATH is the static list route.
                          router.push(CRAFT_REPORT_TEMPLATES_PATH as Route)
                        }
                      >
                        {t("editor.reportTemplate.manage.label")}
                      </Button>
                    </div>
                  </InputVertical>
                </div>
              </Section>
            </Card>

            <div className="grid grid-cols-1 items-stretch gap-4 md:grid-cols-2">
              <div className={COMPOSER_PANE_CLASS} style={COMPOSER_PANE_STYLE}>
                <Content
                  title={t("editor.catalog.title.text")}
                  sizePreset="main-content"
                  variant="section"
                />
                <InputTypeIn
                  placeholder={t("editor.catalog.search.placeholder")}
                  value={catalogQuery}
                  onChange={(event) => setCatalogQuery(event.target.value)}
                  searchIcon
                />
                <div className="min-h-0 flex-1 overflow-y-auto">
                  {visibleCatalog.length === 0 ? (
                    <div className="flex h-full min-h-24 items-center justify-center">
                      <Text color="text-03">
                        {t("editor.catalog.empty.text")}
                      </Text>
                    </div>
                  ) : (
                    <div className="flex flex-col">
                      {visibleCatalog.map((skill) => {
                        const inTray = skillIds.includes(skill.id);
                        return (
                          <div
                            key={skill.id}
                            className="flex items-center gap-2 rounded-08 px-2 py-1.5 hover:bg-background-tint-02"
                          >
                            <Tooltip
                              side="right"
                              align="start"
                              delayDuration={200}
                              tooltip={
                                <div className="flex max-w-xs flex-col gap-1">
                                  <Text font="main-ui-body" color="inherit">
                                    {skill.name}
                                  </Text>
                                  <Text
                                    font="secondary-body"
                                    color="inherit"
                                  >
                                    {skill.description}
                                  </Text>
                                </div>
                              }
                            >
                              <div className="min-w-0 flex-1 overflow-hidden">
                                <Text font="main-ui-body" nowrap>
                                  {skill.name}
                                </Text>
                                <Text
                                  font="secondary-body"
                                  color="text-03"
                                  maxLines={1}
                                >
                                  {skill.description}
                                </Text>
                              </div>
                            </Tooltip>
                            <div className="shrink-0">
                              {inTray ? (
                                <Tag
                                  title={t("editor.catalog.added.label")}
                                  color="gray"
                                />
                              ) : (
                                <Button
                                  size="sm"
                                  prominence="secondary"
                                  icon={SvgPlus}
                                  disabled={fieldsLocked}
                                  aria-label={t("editor.addSkill.label")}
                                  onClick={() => addSkill(skill.id)}
                                >
                                  {t("editor.addSkill.label")}
                                </Button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div className={COMPOSER_PANE_CLASS} style={COMPOSER_PANE_STYLE}>
                <Content
                  title={t("editor.tray.title.text")}
                  description={t("editor.tray.count.label", {
                    count: traySkills.length,
                  })}
                  sizePreset="main-content"
                  variant="section"
                />
                <div className="min-h-0 flex-1 overflow-y-auto">
                  {traySkills.length === 0 ? (
                    <div className="flex h-full min-h-24 items-center justify-center px-4 text-center">
                      <Text color="text-03">{t("editor.tray.empty.text")}</Text>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1">
                      {traySkills.map((skill, index) => (
                        <div
                          key={skill.id}
                          className="flex items-center gap-2 rounded-08 border border-border-01 px-2 py-1.5"
                        >
                          <Text font="secondary-body" color="text-03" nowrap>
                            {String(index + 1).padStart(2, "0")}
                          </Text>
                          <Tooltip tooltip={skill.name} side="top">
                            <div className="min-w-0 flex-1 overflow-hidden">
                              <Text font="main-ui-body" nowrap>
                                {skill.name}
                              </Text>
                            </div>
                          </Tooltip>
                          <div className="flex items-center gap-0.5">
                            <Button
                              size="sm"
                              prominence="tertiary"
                              icon={SvgChevronUp}
                              disabled={fieldsLocked || index === 0}
                              aria-label={t("editor.moveUp.ariaLabel")}
                              onClick={() => moveSkill(skill.id, -1)}
                            />
                            <Button
                              size="sm"
                              prominence="tertiary"
                              icon={SvgChevronDown}
                              disabled={
                                fieldsLocked || index === traySkills.length - 1
                              }
                              aria-label={t("editor.moveDown.ariaLabel")}
                              onClick={() => moveSkill(skill.id, 1)}
                            />
                            <Button
                              size="sm"
                              prominence="tertiary"
                              icon={SvgTrash}
                              disabled={fieldsLocked}
                              aria-label={t("editor.removeSkill.ariaLabel", {
                                name: skill.name,
                              })}
                              onClick={() => removeSkill(skill.id)}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                prominence="tertiary"
                disabled={fieldsLocked}
                icon={SvgPlus}
                onClick={() =>
                  setConditionals((current) => [...current, emptyConditional()])
                }
              >
                {t("editor.conditional.add.label")}
              </Button>
              <Button
                size="sm"
                prominence="tertiary"
                onClick={() => setPreviewOpen((open) => !open)}
              >
                {t("editor.preview.title")}
              </Button>
            </div>

            {conditionals.length > 0 ? (
              <Card border="solid" rounding={4} padding={3} background="light">
                <Section gap={2} alignItems="stretch">
                  <Content
                    title={t("editor.conditional.title.text")}
                    sizePreset="main-content"
                    variant="section"
                  />
                  {conditionals.map((draft, index) => (
                    <div
                      key={`${index}-${draft.skillId}`}
                      className="grid grid-cols-1 items-center gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
                    >
                      <InputTypeIn
                        value={draft.keywords}
                        onChange={(event) => {
                          const value = event.target.value;
                          setConditionals((current) =>
                            current.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, keywords: value }
                                : item
                            )
                          );
                        }}
                        placeholder={t(
                          "editor.conditional.keywords.placeholder"
                        )}
                        variant={fieldsLocked ? "disabled" : "primary"}
                      />
                      <InputTypeIn
                        value={draft.intent}
                        onChange={(event) => {
                          const value = event.target.value;
                          setConditionals((current) =>
                            current.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, intent: value }
                                : item
                            )
                          );
                        }}
                        placeholder={t(
                          "editor.conditional.intent.placeholder"
                        )}
                        variant={fieldsLocked ? "disabled" : "primary"}
                      />
                      <InputSelect
                        value={draft.skillId || undefined}
                        onValueChange={(value) => {
                          setConditionals((current) =>
                            current.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, skillId: value }
                                : item
                            )
                          );
                        }}
                        disabled={fieldsLocked}
                      >
                        <InputSelect.Trigger
                          placeholder={t(
                            "editor.conditional.skill.placeholder"
                          )}
                        />
                        <InputSelect.Content>
                          {allSkills.map((skill) => (
                            <InputSelect.Item key={skill.id} value={skill.id}>
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
                        aria-label={t("editor.conditional.remove.ariaLabel")}
                        onClick={() =>
                          setConditionals((current) =>
                            current.filter(
                              (_, itemIndex) => itemIndex !== index
                            )
                          )
                        }
                      />
                    </div>
                  ))}
                </Section>
              </Card>
            ) : null}

            {previewOpen ? (
              <Card border="solid" rounding={4} padding={3} background="heavy">
                <pre className="m-0 max-h-36 overflow-y-auto whitespace-pre-wrap wrap-break-word font-mono text-xs leading-5 text-text-03">
                  {preview}
                </pre>
              </Card>
            ) : null}
          </div>
        )}
      </SettingsLayouts.Body>

      <ShareScenarioModal
        scenario={scenario ?? null}
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        onSaved={() => {
          void refresh();
        }}
      />

      <UnsavedChangesModal
        open={unsavedChanges.confirmationOpen}
        onCancel={unsavedChanges.cancelLeave}
        onDiscard={unsavedChanges.discardAndLeave}
      />
    </SettingsLayouts.Root>
  );
}
