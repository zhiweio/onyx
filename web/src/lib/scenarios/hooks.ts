"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";
import { toast } from "@opal/layouts";
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
  canEditScenario,
  collectCustomScenarioDomains,
  emptyPlaybookDraft,
  normalizeScenarioDomain,
  parsePlaybookDraft,
  playbookToRules,
  type Scenario,
  type ScenarioConditionalRule,
} from "@/lib/scenarios/types";
import type { Skill } from "@/lib/skills/types";
import {
  CRAFT_PATH,
  CRAFT_SCENARIOS_PATH,
} from "@/app/craft/v1/constants";
import { CRAFT_SEARCH_PARAM_NAMES } from "@/app/craft/services/searchParams";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";
import {
  createCatalogEntry,
  updateCatalogEntry,
} from "@/lib/system-catalog/api";
import {
  useCatalogEntries,
  useCatalogItem,
} from "@/lib/system-catalog/hooks";
import type {
  CatalogScenarioCreateInput,
  CatalogPatchInput,
} from "@/lib/system-catalog/api";
import type {
  SystemCatalogCategory,
  SystemReportTemplateItem,
  SystemScenarioItem,
  SystemSkillItem,
} from "@/lib/system-catalog/types";
import type {
  ConditionalDraft,
  ScenarioDraft,
  SkillOption,
  TemplateOption,
} from "@/sections/scenarios/editor/types";
import {
  conditionalsToRules,
  draftFingerprint,
} from "@/sections/scenarios/editor/types";

function skillsFromList(
  data: { builtins?: Skill[]; customs?: Skill[] } | undefined
): Skill[] {
  return [...(data?.builtins ?? []), ...(data?.customs ?? [])];
}

function parseConditionals(
  rules: { conditional?: ScenarioConditionalRule[] } | undefined,
  keyField: "add_skill_ids" | "add_skill_slugs"
): ConditionalDraft[] {
  return (rules?.conditional ?? []).map((rule) => ({
    keywords: (rule.if.query_contains_any ?? []).join(", "),
    intent: rule.if.intent ?? "",
    skillKey: (rule[keyField] ?? [])[0] ?? "",
  }));
}

function emptyDraft(overrides: Partial<ScenarioDraft> = {}): ScenarioDraft {
  return {
    name: "",
    description: "",
    skillKeys: [],
    reportTemplate: "",
    domain: "custom",
    playbook: emptyPlaybookDraft(),
    extras: {},
    slug: "",
    category: "GENERAL",
    tags: [],
    ...overrides,
  };
}

function draftFromUserScenario(scenario: Scenario): {
  draft: ScenarioDraft;
  conditionals: ConditionalDraft[];
} {
  const { playbook, extras } = parsePlaybookDraft(scenario.rules);
  return {
    draft: emptyDraft({
      name: scenario.name,
      description: scenario.description,
      skillKeys: scenario.skill_ids,
      reportTemplate: scenario.report_template ?? "",
      domain: normalizeScenarioDomain(scenario.rules.domain),
      playbook,
      extras,
    }),
    conditionals: parseConditionals(scenario.rules, "add_skill_ids"),
  };
}

function draftFromCatalogScenario(item: SystemScenarioItem): {
  draft: ScenarioDraft;
  conditionals: ConditionalDraft[];
} {
  const { playbook, extras } = parsePlaybookDraft(item.rules);
  return {
    draft: emptyDraft({
      name: item.name,
      description: item.description,
      skillKeys: item.skill_slugs,
      reportTemplate: item.report_template_slug ?? "",
      domain:
        typeof item.rules.domain === "string"
          ? normalizeScenarioDomain(item.rules.domain)
          : "custom",
      playbook,
      extras,
      slug: item.slug,
      category: item.category,
      tags: item.tags,
    }),
    conditionals: parseConditionals(
      item.rules as { conditional?: ScenarioConditionalRule[] },
      "add_skill_slugs"
    ),
  };
}

export function useUserScenarioEditor(scenarioId?: string) {
  const t = useTranslations("craft.scenarioEditor");
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
  const [draft, setDraft] = useState<ScenarioDraft>(emptyDraft);
  const [conditionals, setConditionals] = useState<ConditionalDraft[]>([]);
  const [baseline, setBaseline] = useState("");
  const [hydratedId, setHydratedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [customizing, setCustomizing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  useEffect(() => {
    if (isCreating && baseline === "") {
      setBaseline(draftFingerprint(emptyDraft(), []));
    }
  }, [baseline, isCreating]);

  useEffect(() => {
    if (!scenario || scenario.id === hydratedId) return;
    const next = draftFromUserScenario(scenario);
    setDraft(next.draft);
    setConditionals(next.conditionals);
    setBaseline(draftFingerprint(next.draft, next.conditionals));
    setHydratedId(scenario.id);
  }, [hydratedId, scenario]);

  const isDirty =
    baseline !== "" && draftFingerprint(draft, conditionals) !== baseline;
  const unsavedChanges = useUnsavedChangesGuard({ isDirty });
  const canEdit = isCreating || (scenario ? canEditScenario(scenario) : false);
  const fieldsLocked = !canEdit || saving;
  const canSave =
    canEdit &&
    !saving &&
    isDirty &&
    draft.name.trim().length > 0 &&
    draft.skillKeys.length >= 1;

  function onDraftChange(patch: Partial<ScenarioDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function leaveEditor() {
    router.push(CRAFT_SCENARIOS_PATH as Route);
  }

  function handleCancel() {
    if (saving) return;
    unsavedChanges.requestLeave(leaveEditor);
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
        name: draft.name.trim(),
        description: draft.description.trim(),
        skill_ids: draft.skillKeys,
        rules: playbookToRules({
          domain: draft.domain,
          playbook: draft.playbook,
          extras: draft.extras,
          conditionals: conditionalsToRules(conditionals, "add_skill_ids"),
        }),
        report_template: draft.reportTemplate.trim() || null,
      };
      const saved =
        isCreating || !scenarioId
          ? await createScenario(payload)
          : await updateScenario(scenarioId, payload);
      setBaseline(draftFingerprint(draft, conditionals));
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
          : t("toasts.saveFailed.message")
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

  return {
    mode: "user" as const,
    isCreating,
    isLoading,
    error,
    canEdit,
    fieldsLocked,
    draft,
    conditionals,
    onDraftChange,
    onConditionalsChange: setConditionals,
    skillCatalog: allSkills.map((skill) => ({
      key: skill.id,
      name: skill.name,
      description: skill.description,
    })),
    templates: reportTemplates.map((item) => ({
      slug: item.slug,
      name: item.name,
      description: item.description,
    })),
    knownCustomDomains: collectCustomScenarioDomains(allScenarios),
    isDirty,
    onCancel: handleCancel,
    onSave: () => void handleSave(),
    saving,
    canSave,
    saveTooltip: !draft.name.trim()
      ? t("validation.name")
      : draft.skillKeys.length < 1
        ? t("validation.skills")
        : undefined,
    onShare: () => setShareOpen(true),
    onStartRun: () => void handleStart(),
    starting,
    onCustomize: () => void handleCustomize(),
    customizing,
    shareOpen,
    setShareOpen,
    scenario,
    refresh,
    unsavedChanges,
  };
}

export function useCatalogScenarioEditor(entryId?: string) {
  const t = useTranslations("craft.scenarioEditor");
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const isCreating = entryId === undefined;
  const {
    data: item,
    error,
    isLoading,
    refresh,
  } = useCatalogItem<SystemScenarioItem>("scenarios", entryId);
  const { data: catalogSkills } = useCatalogEntries<SystemSkillItem>("skills");
  const { data: catalogTemplates } =
    useCatalogEntries<SystemReportTemplateItem>("report-templates");

  const [draft, setDraft] = useState<ScenarioDraft>(emptyDraft);
  const [conditionals, setConditionals] = useState<ConditionalDraft[]>([]);
  const [baseline, setBaseline] = useState("");
  const [hydratedId, setHydratedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isCreating && baseline === "") {
      setBaseline(draftFingerprint(emptyDraft(), []));
    }
  }, [baseline, isCreating]);

  useEffect(() => {
    if (!item || item.id === hydratedId) return;
    const next = draftFromCatalogScenario(item);
    setDraft(next.draft);
    setConditionals(next.conditionals);
    setBaseline(draftFingerprint(next.draft, next.conditionals));
    setHydratedId(item.id);
  }, [hydratedId, item]);

  const isDirty =
    baseline !== "" && draftFingerprint(draft, conditionals) !== baseline;
  const unsavedChanges = useUnsavedChangesGuard({ isDirty });
  const fieldsLocked = saving;
  const slugReady = !isCreating || draft.slug.trim().length > 0;
  const canSave =
    !saving &&
    isDirty &&
    draft.name.trim().length > 0 &&
    draft.skillKeys.length >= 1 &&
    slugReady;

  function onDraftChange(patch: Partial<ScenarioDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function leaveEditor() {
    router.push("/admin/craft/catalog" as Route);
  }

  function handleCancel() {
    if (saving) return;
    unsavedChanges.requestLeave(leaveEditor);
  }

  async function refreshLists(saved: SystemScenarioItem) {
    await mutate(`/api/admin/craft/catalog/scenarios`);
    await mutate(`/api/admin/craft/catalog/scenarios/${saved.id}`, saved, {
      revalidate: false,
    });
  }

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    try {
      const rules = playbookToRules({
        domain: draft.domain,
        playbook: draft.playbook,
        extras: draft.extras,
        conditionals: conditionalsToRules(conditionals, "add_skill_slugs"),
      });
      const saved = isCreating
        ? await createCatalogEntry<SystemScenarioItem>("scenarios", {
            slug: draft.slug.trim(),
            name: draft.name.trim(),
            description: draft.description.trim() || draft.name.trim(),
            category: draft.category,
            tags: draft.tags,
            rules,
            skill_slugs: draft.skillKeys,
            report_template_slug: draft.reportTemplate.trim() || null,
          } satisfies CatalogScenarioCreateInput)
        : await updateCatalogEntry<SystemScenarioItem>("scenarios", entryId, {
            name: draft.name.trim(),
            description: draft.description.trim() || draft.name.trim(),
            category: draft.category,
            tags: draft.tags,
            rules,
            skill_slugs: draft.skillKeys,
            report_template_slug: draft.reportTemplate.trim() || null,
            clear_report_template: !draft.reportTemplate.trim(),
          } satisfies CatalogPatchInput);
      setBaseline(draftFingerprint(draft, conditionals));
      await refreshLists(saved);
      toast.success(
        isCreating
          ? t("toasts.catalogCreated.message")
          : t("toasts.catalogSaved.message")
      );
      if (isCreating) {
        router.replace(
          `/admin/craft/catalog/scenarios/edit/${saved.id}` as Route
        );
      }
    } catch (saveError) {
      console.error(saveError);
      toast.error(
        saveError instanceof Error
          ? saveError.message
          : t("toasts.saveFailed.message")
      );
    } finally {
      setSaving(false);
    }
  }

  const skillCatalog: SkillOption[] = catalogSkills.map((skill) => ({
    key: skill.slug,
    name: skill.name,
    description: skill.description,
  }));
  const templates: TemplateOption[] = catalogTemplates.map((item) => ({
    slug: item.slug,
    name: item.name,
    description: item.description,
  }));

  return {
    mode: "catalog" as const,
    isCreating,
    isLoading,
    error,
    canEdit: true,
    fieldsLocked,
    draft,
    conditionals,
    onDraftChange,
    onConditionalsChange: setConditionals,
    skillCatalog,
    templates,
    isDirty,
    onCancel: handleCancel,
    onSave: () => void handleSave(),
    saving,
    canSave,
    saveTooltip: !draft.name.trim()
      ? t("validation.name")
      : draft.skillKeys.length < 1
        ? t("validation.skills")
        : !slugReady
          ? t("validation.slug")
          : undefined,
    item,
    refresh,
    unsavedChanges,
  };
}
