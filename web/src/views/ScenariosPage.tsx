"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { Button, InputTypeIn, MessageCard, Text } from "@opal/components";
import {
  ConfirmationModalLayout,
  IllustrationContent,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { SvgPlus, SvgShare, SvgSimpleLoader, SvgTrash } from "@opal/icons";
import TextSeparator from "@/refresh-components/TextSeparator";
import useOnMount from "@/hooks/useOnMount";
import useScenarios from "@/hooks/useScenarios";
import useUserSkills from "@/hooks/useUserSkills";
import { deleteScenario, duplicateScenario } from "@/lib/scenarios/api";
import { startScenarioRun } from "@/lib/scenarios/run";
import {
  collectCustomScenarioDomains,
  isBuiltinScenarioDomain,
  isUncategorizedDomain,
  scenarioDomain,
  scenarioDomainMessageKey,
  type Scenario,
} from "@/lib/scenarios/types";
import ScenarioCard from "@/sections/cards/ScenarioCard";
import ShareScenarioModal from "@/sections/modals/scenarios/ShareScenarioModal";
import {
  CRAFT_PATH,
  CRAFT_SCENARIOS_PATH,
} from "@/app/craft/v1/constants";
import { CRAFT_SEARCH_PARAM_NAMES } from "@/app/craft/services/searchParams";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

export default function ScenariosPage() {
  const t = useTranslations("craft.scenarios");
  const router = useRouter();
  const { data: scenarios, error, isLoading, refresh } = useScenarios();
  const { data: skillsData } = useUserSkills();
  const refreshSessionHistory = useBuildSessionStore(
    (state) => state.refreshSessionHistory
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [domainFilter, setDomainFilter] = useState<string>("all");
  const [shareTarget, setShareTarget] = useState<Scenario | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Scenario | null>(null);
  const [startingId, setStartingId] = useState<string | null>(null);
  const [customizingId, setCustomizingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useOnMount(() => {
    searchInputRef.current?.focus();
  });

  const skillNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const skill of [
      ...(skillsData?.builtins ?? []),
      ...(skillsData?.customs ?? []),
    ]) {
      map.set(skill.id, skill.name);
    }
    return map;
  }, [skillsData]);

  const domainFilters = useMemo(() => {
    const customs = collectCustomScenarioDomains(scenarios);
    const hasUncategorized = scenarios.some((scenario) =>
      isUncategorizedDomain(scenarioDomain(scenario))
    );
    return [
      "all",
      "tax",
      "biomed",
      ...customs,
      ...(hasUncategorized ? ["custom"] : []),
    ];
  }, [scenarios]);

  const visibleScenarios = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return scenarios.filter((scenario) => {
      const domain = scenarioDomain(scenario);
      if (domainFilter !== "all" && domain !== domainFilter) {
        return false;
      }
      if (!query) return true;
      const skillNames = scenario.skill_ids
        .map((id) => skillNameById.get(id) ?? "")
        .join(" ");
      return (
        scenario.name.toLowerCase().includes(query) ||
        scenario.description.toLowerCase().includes(query) ||
        skillNames.toLowerCase().includes(query)
      );
    });
  }, [domainFilter, scenarios, searchQuery, skillNameById]);

  function skillNamesFor(scenario: Scenario): string[] {
    return scenario.skill_ids.map(
      (id) => skillNameById.get(id) ?? id.slice(0, 8)
    );
  }

  function openEditor(scenario: Scenario) {
    router.push(`${CRAFT_SCENARIOS_PATH}/edit/${scenario.id}` as Route);
  }

  async function handleCustomize(scenario: Scenario) {
    setCustomizingId(scenario.id);
    try {
      const copied = await duplicateScenario(scenario.id);
      await refresh();
      toast.success(t("toasts.duplicated.message"));
      router.push(`${CRAFT_SCENARIOS_PATH}/edit/${copied.id}` as Route);
    } catch (customizeError) {
      console.error(customizeError);
      toast.error(
        customizeError instanceof Error
          ? customizeError.message
          : t("toasts.duplicateFailed.message")
      );
    } finally {
      setCustomizingId(null);
    }
  }

  async function handleStart(scenario: Scenario) {
    setStartingId(scenario.id);
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
      setStartingId(null);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteScenario(deleteTarget.id);
      setDeleteTarget(null);
      await refresh();
      toast.success(t("toasts.deleted.message"));
    } catch (deleteError) {
      console.error(deleteError);
      toast.error(
        deleteError instanceof Error
          ? deleteError.message
          : t("toasts.shareFailed.message")
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <SettingsLayouts.Root data-testid="ScenariosPage/container">
      <SettingsLayouts.Header
        icon={SvgShare}
        title={t("page.title.text")}
        description={t("page.description.text")}
        rightChildren={
          <Button
            icon={SvgPlus}
            onClick={() =>
              router.push(`${CRAFT_SCENARIOS_PATH}/new` as Route)
            }
          >
            {t("page.createButton.label")}
          </Button>
        }
      >
        <InputTypeIn
          ref={searchInputRef}
          placeholder={t("page.search.placeholder")}
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          searchIcon
        />
        <div className="flex flex-wrap gap-2 pt-2">
          {domainFilters.map((domain) => (
            <Button
              key={domain}
              prominence={domainFilter === domain ? "primary" : "secondary"}
              size="sm"
              onClick={() => setDomainFilter(domain)}
            >
              {domain === "all" ||
              isBuiltinScenarioDomain(domain) ||
              domain === "custom"
                ? t(scenarioDomainMessageKey(domain))
                : domain}
            </Button>
          ))}
        </div>
      </SettingsLayouts.Header>

      <SettingsLayouts.Body>
        {isLoading && <SvgSimpleLoader />}

        {error && !isLoading && (
          <MessageCard
            variant="error"
            title={t("error.title")}
            description={t("error.description")}
          />
        )}

        {!isLoading && !error && (
          <>
            {visibleScenarios.length === 0 ? (
              <IllustrationContent
                illustration={SvgNoResult}
                title={
                  scenarios.length === 0
                    ? t("empty.none.title")
                    : t("empty.search.title")
                }
                description={
                  scenarios.length === 0
                    ? t("empty.none.description")
                    : t("empty.search.description")
                }
              />
            ) : (
              <>
                <section className="flex flex-col gap-2">
                  <Text font="secondary-body" color="text-03">
                    {t("page.browse.title")}
                  </Text>
                  <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-2">
                    {visibleScenarios.map((scenario) => (
                      <ScenarioCard
                        key={scenario.id}
                        scenario={scenario}
                        skillNames={skillNamesFor(scenario)}
                        startPending={startingId === scenario.id}
                        customizePending={customizingId === scenario.id}
                        onClick={openEditor}
                        onEdit={openEditor}
                        onCustomize={(item) => void handleCustomize(item)}
                        onShare={setShareTarget}
                        onDelete={setDeleteTarget}
                        onStart={(item) => void handleStart(item)}
                      />
                    ))}
                  </div>
                </section>
                <TextSeparator
                  text={t("page.count.label", {
                    count: visibleScenarios.length,
                  })}
                />
              </>
            )}
          </>
        )}
      </SettingsLayouts.Body>

      <ShareScenarioModal
        scenario={shareTarget}
        open={shareTarget !== null}
        onClose={() => setShareTarget(null)}
        onSaved={() => {
          void refresh();
        }}
      />

      {deleteTarget && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("delete.title", { name: deleteTarget.name })}
          description={t("delete.description")}
          onClose={deleting ? undefined : () => setDeleteTarget(null)}
          submit={
            <Button
              variant="danger"
              disabled={deleting}
              onClick={() => void handleDelete()}
            >
              {t("delete.confirm.label")}
            </Button>
          }
        />
      )}
    </SettingsLayouts.Root>
  );
}
