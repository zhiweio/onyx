"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { Button, InputTypeIn, InputTextArea, MessageCard, Text } from "@opal/components";
import {
  ConfirmationModalLayout,
  IllustrationContent,
  InputVertical,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { SvgFolder, SvgPlus, SvgSimpleLoader, SvgTrash } from "@opal/icons";
import TextSeparator from "@/refresh-components/TextSeparator";
import { Section } from "@/layouts/general-layouts";
import useOnMount from "@/hooks/useOnMount";
import { useCraftProjects } from "@/lib/craft-projects/hooks";
import {
  createCraftProject,
  deleteCraftProject,
  startCraftProjectSession,
} from "@/lib/craft-projects/api";
import type { CraftProject } from "@/lib/craft-projects/types";
import { isImplicitUntitledProject } from "@/lib/craft-projects/display";
import CraftProjectCard from "@/sections/cards/CraftProjectCard";
import {
  CRAFT_PATH,
  CRAFT_PROJECTS_PATH,
} from "@/app/craft/v1/constants";
import { CRAFT_SEARCH_PARAM_NAMES } from "@/app/craft/services/searchParams";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

export default function CraftProjectsPage() {
  const t = useTranslations("craft.projects");
  const router = useRouter();
  const { data: projects, error, isLoading, refresh } = useCraftProjects();
  const refreshSessionHistory = useBuildSessionStore(
    (state) => state.refreshSessionHistory
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newInstructions, setNewInstructions] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<CraftProject | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [startingId, setStartingId] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useOnMount(() => {
    searchInputRef.current?.focus();
  });

  const visibleProjects = useMemo(() => {
    const realProjects = projects.filter(
      (project) => !isImplicitUntitledProject(project)
    );
    const query = searchQuery.trim().toLowerCase();
    if (!query) return realProjects;
    return realProjects.filter(
      (project) =>
        project.name.toLowerCase().includes(query) ||
        project.description.toLowerCase().includes(query)
    );
  }, [projects, searchQuery]);

  function openProject(project: CraftProject) {
    // SAFETY: project ids are UUID path segments under /craft/v1/projects.
    router.push(`${CRAFT_PROJECTS_PATH}/${project.id}` as Route);
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await createCraftProject({
        name,
        description: newDescription.trim(),
        instructions: newInstructions.trim() || null,
      });
      setCreateOpen(false);
      setNewName("");
      setNewDescription("");
      setNewInstructions("");
      await refresh();
      toast.success(t("toasts.created.message"));
      // SAFETY: created.id is the UUID of the project that was just saved.
      router.push(`${CRAFT_PROJECTS_PATH}/${created.id}` as Route);
    } catch (createError) {
      console.error(createError);
      toast.error(
        createError instanceof Error
          ? createError.message
          : t("toasts.createFailed.message")
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleContinue(project: CraftProject) {
    setStartingId(project.id);
    try {
      const session = await startCraftProjectSession(project.id, project.name);
      await refreshSessionHistory();
      // SAFETY: session.id is a UUID query value on the Craft home route.
      router.push(
        `${CRAFT_PATH}?${CRAFT_SEARCH_PARAM_NAMES.SESSION_ID}=${session.id}` as Route
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
      await deleteCraftProject(deleteTarget.id);
      setDeleteTarget(null);
      await refresh();
      toast.success(t("toasts.deleted.message"));
    } catch (deleteError) {
      console.error(deleteError);
      toast.error(
        deleteError instanceof Error
          ? deleteError.message
          : t("toasts.deleteFailed.message")
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <SettingsLayouts.Root data-testid="CraftProjectsPage/container">
      <SettingsLayouts.Header
        icon={SvgFolder}
        title={t("page.title.text")}
        description={t("page.description.text")}
        rightChildren={
          <Button icon={SvgPlus} onClick={() => setCreateOpen(true)}>
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
            {visibleProjects.length === 0 ? (
              <IllustrationContent
                illustration={SvgNoResult}
                title={
                  projects.length === 0
                    ? t("empty.none.title")
                    : t("empty.search.title")
                }
                description={
                  projects.length === 0
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
                    {visibleProjects.map((project) => (
                      <CraftProjectCard
                        key={project.id}
                        project={project}
                        continuePending={startingId === project.id}
                        onClick={openProject}
                        onContinue={(item) => void handleContinue(item)}
                        onDelete={setDeleteTarget}
                      />
                    ))}
                  </div>
                </section>
                <TextSeparator
                  text={t("page.count.label", {
                    count: visibleProjects.length,
                  })}
                />
              </>
            )}
          </>
        )}
      </SettingsLayouts.Body>

      {createOpen && (
        <ConfirmationModalLayout
          icon={SvgFolder}
          title={t("create.title")}
          onClose={creating ? undefined : () => setCreateOpen(false)}
          submit={
            <Button
              disabled={creating || !newName.trim()}
              onClick={() => void handleCreate()}
            >
              {t("create.submit.label")}
            </Button>
          }
        >
          <Section gap={3}>
            <InputVertical title={t("create.name.label")} withLabel>
              <InputTypeIn
                placeholder={t("create.name.placeholder")}
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                variant={creating ? "disabled" : undefined}
              />
            </InputVertical>
            <InputVertical title={t("create.description.label")} withLabel>
              <InputTypeIn
                placeholder={t("create.description.placeholder")}
                value={newDescription}
                onChange={(event) => setNewDescription(event.target.value)}
                variant={creating ? "disabled" : undefined}
              />
            </InputVertical>
            <InputVertical title={t("create.instructions.label")} withLabel>
              <InputTextArea
                rows={4}
                value={newInstructions}
                onChange={(event) => setNewInstructions(event.target.value)}
                placeholder={t("create.instructions.placeholder")}
                autoResize
                maxRows={8}
                variant={creating ? "disabled" : undefined}
              />
            </InputVertical>
          </Section>
        </ConfirmationModalLayout>
      )}

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
