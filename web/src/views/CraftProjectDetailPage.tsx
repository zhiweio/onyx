"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useFormatter, useTranslations } from "next-intl";
import {
  Button,
  Card,
  InputTextArea,
  LineItemButton,
  MessageCard,
  Text,
  type TagColor,
} from "@opal/components";
import {
  ConfirmationModalLayout,
  Content,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import {
  SvgEdit,
  SvgFileText,
  SvgFolder,
  SvgPlayCircle,
  SvgSimpleLoader,
  SvgSliders,
  SvgTrash,
} from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import CraftProjectFiles from "@/app/craft/components/CraftProjectFiles";
import CraftProjectSandboxCard from "@/app/craft/components/CraftProjectSandboxCard";
import {
  useCraftProject,
  useRefreshCraftProjects,
} from "@/lib/craft-projects/hooks";
import {
  deleteCraftProject,
  resetCraftProjectSandbox,
  startCraftProjectSession,
  updateCraftProject,
} from "@/lib/craft-projects/api";
import type { CraftProjectSession } from "@/lib/craft-projects/types";
import {
  compareProjectSessions,
  isKnownSessionRole,
  isProjectMainSession,
  parseSessionLane,
  projectHeadline,
  projectSessionDisplayStatus,
  type CraftProjectSessionStatusKey,
} from "@/lib/craft-projects/display";
import { CRAFT_PATH, CRAFT_PROJECTS_PATH } from "@/app/craft/v1/constants";
import { CRAFT_SEARCH_PARAM_NAMES } from "@/app/craft/services/searchParams";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

const SESSION_STATUS_COLOR: Record<CraftProjectSessionStatusKey, TagColor> = {
  initializing: "amber",
  active: "green",
  idle: "gray",
  failed: "red",
};

interface CraftProjectDetailPageProps {
  projectId: string;
}

function sessionTitle(
  session: CraftProjectSession,
  t: ReturnType<typeof useTranslations>
): { title: string; description: string; tooltip: string } {
  const fallback = session.name || session.id.slice(0, 8);
  const { role, goal } = parseSessionLane(session.name);
  const tooltip = session.name || session.id;
  if (role && goal) {
    const roleLabel = isKnownSessionRole(role)
      ? t(`detail.sessionRole.${role}`)
      : role;
    return { title: roleLabel, description: "", tooltip };
  }
  return { title: fallback, description: "", tooltip };
}

export default function CraftProjectDetailPage({
  projectId,
}: CraftProjectDetailPageProps) {
  const t = useTranslations("craft.projects");
  const format = useFormatter();
  const router = useRouter();
  const { data, error, isLoading, refresh } = useCraftProject(projectId);
  const refreshProjects = useRefreshCraftProjects();
  const refreshSessionHistory = useBuildSessionStore(
    (state) => state.refreshSessionHistory
  );
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [pendingName, setPendingName] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [resettingSandbox, setResettingSandbox] = useState(false);

  useEffect(() => {
    if (!data) return;
    setDescription(data.description);
    setInstructions(data.instructions ?? "");
  }, [data]);

  const detailsDirty =
    data !== undefined && description.trim() !== data.description;
  const instructionsDirty =
    data !== undefined &&
    (instructions.trim() || null) !== (data.instructions ?? null);

  async function persistProject(patch: {
    name?: string;
    description?: string;
    instructions?: string | null;
  }): Promise<boolean> {
    if (!data) return false;
    setSaving(true);
    try {
      await updateCraftProject(data.id, patch);
      await refresh();
      await refreshProjects(data.id);
      toast.success(
        patch.name ? t("toasts.renamed.message") : t("toasts.saved.message")
      );
      return true;
    } catch (saveError) {
      console.error(saveError);
      toast.error(
        saveError instanceof Error
          ? saveError.message
          : patch.name
            ? t("toasts.renameFailed.message")
            : t("toasts.saveFailed.message")
      );
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveInstructions() {
    if (!data) return;
    await persistProject({
      instructions: instructions.trim() || null,
    });
  }

  async function handleSaveDetails() {
    if (!data) return;
    await persistProject({
      description: description.trim(),
    });
  }

  function handleTitleChange(newTitle: string) {
    const next = newTitle.trim();
    if (!data || !next || next === data.name) return;
    setPendingName(next);
  }

  async function handleConfirmRename() {
    if (!pendingName) return;
    setRenaming(true);
    try {
      const saved = await persistProject({ name: pendingName });
      if (saved) setPendingName(null);
    } finally {
      setRenaming(false);
    }
  }

  async function handleResetSandbox(migrateOutputs: boolean) {
    if (!data) return;
    setResettingSandbox(true);
    try {
      await resetCraftProjectSandbox(data.id, migrateOutputs);
      await refresh();
      toast.success(t("toasts.sandboxReset.message"));
    } catch (resetError) {
      console.error(resetError);
      toast.error(
        resetError instanceof Error
          ? resetError.message
          : t("toasts.sandboxResetFailed.message")
      );
    } finally {
      setResettingSandbox(false);
    }
  }

  async function handleStart() {
    if (!data) return;
    setStarting(true);
    try {
      const session = await startCraftProjectSession(data.id, data.name);
      await refreshSessionHistory();
      // SAFETY: session.id is a UUID query value on the Craft home route.
      router.push(
        `${CRAFT_PATH}?${CRAFT_SEARCH_PARAM_NAMES.SESSION_ID}=${session.id}` as Route
      );
    } catch (startError) {
      console.error(startError);
      toast.error(t("toasts.openFailed.message"));
    } finally {
      setStarting(false);
    }
  }

  async function handleDeleteProject() {
    if (!data) return;
    setDeleting(true);
    try {
      await deleteCraftProject(data.id);
      await refreshProjects();
      await refreshSessionHistory();
      toast.success(t("toasts.deleted.message"));
      // SAFETY: CRAFT_PROJECTS_PATH is the static projects list route.
      router.push(CRAFT_PROJECTS_PATH as Route);
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

  function openSession(session: CraftProjectSession) {
    // SAFETY: session.id is a UUID query value on the Craft home route.
    router.push(
      `${CRAFT_PATH}?${CRAFT_SEARCH_PARAM_NAMES.SESSION_ID}=${session.id}` as Route
    );
  }

  const sessions = useMemo(() => {
    const items = (data?.sessions ?? []).filter(isProjectMainSession);
    items.sort(compareProjectSessions);
    return items;
  }, [data?.sessions]);

  const hasSessions = sessions.length > 0;
  const startLabel = hasSessions
    ? t("detail.newChat.label")
    : t("detail.startChat.label");
  const headline = projectHeadline(data?.name ?? t("page.title.text"));
  const headerDescription = (data?.description ?? "").trim();

  return (
    <SettingsLayouts.Root
      width="lg"
      data-testid="CraftProjectDetailPage/container"
    >
      <SettingsLayouts.Header
        icon={SvgFolder}
        title={data ? headline.full : headline.title}
        description={headerDescription || undefined}
        editable={Boolean(data)}
        onTitleChange={handleTitleChange}
        backButton={() => {
          router.push(CRAFT_PROJECTS_PATH as Route);
        }}
        rightChildren={
          <div className="flex items-center gap-1">
            <Button
              prominence="tertiary"
              icon={SvgTrash}
              onClick={() => setDeleteOpen(true)}
              disabled={!data}
            >
              {t("delete.confirm.label")}
            </Button>
            <Button
              icon={SvgPlayCircle}
              disabled={!data || starting}
              onClick={() => void handleStart()}
            >
              {startLabel}
            </Button>
          </div>
        }
      />

      <SettingsLayouts.Body>
        {isLoading && <SvgSimpleLoader />}

        {error && !isLoading && (
          <MessageCard
            variant="error"
            title={t("error.title")}
            description={t("error.description")}
          />
        )}

        {data && !isLoading && (
          <Section
            gap={4}
            alignItems="stretch"
            justifyContent="start"
            height="auto"
          >
            <CraftProjectFiles
              projectId={data.id}
              files={data.files ?? []}
              onChanged={refresh}
            />

            <CraftProjectSandboxCard
              sandbox={data.sandbox}
              resetting={resettingSandbox}
              onReset={handleResetSandbox}
            />

            <Card border="solid" rounding={4} padding={4}>
              <Section
                gap={2}
                alignItems="stretch"
                justifyContent="start"
                height="auto"
              >
                <Content
                  icon={SvgPlayCircle}
                  title={t("detail.sessions.title")}
                  description={t("card.sessionCount.label", {
                    count: sessions.length,
                  })}
                  sizePreset="main-ui"
                  variant="section"
                  width="full"
                />
                {hasSessions ? (
                  <div className="flex w-full min-w-0 flex-col gap-0.5">
                    {sessions.map((session) => {
                      const statusKey = projectSessionDisplayStatus(session);
                      const copy = sessionTitle(session, t);
                      const activity = format.relativeTime(
                        new Date(session.last_activity_at)
                      );
                      const description = [copy.description, activity]
                        .filter(Boolean)
                        .join(" · ");
                      return (
                        <LineItemButton
                          key={session.id}
                          sizePreset="main-ui"
                          variant="section"
                          rounding={2}
                          width="full"
                          icon={SvgPlayCircle}
                          title={copy.title}
                          titleMaxLines={1}
                          description={description || undefined}
                          descriptionMaxLines={1}
                          tooltip={copy.tooltip}
                          tag={{
                            color: SESSION_STATUS_COLOR[statusKey],
                            title: t(`detail.sessionStatus.${statusKey}`),
                          }}
                          onClick={() => openSession(session)}
                        />
                      );
                    })}
                  </div>
                ) : (
                  <Text font="secondary-body" color="text-03">
                    {t("detail.emptySessions.description")}
                  </Text>
                )}
              </Section>
            </Card>

            <Card border="solid" rounding={4} padding={4}>
              <Section
                gap={3}
                alignItems="stretch"
                justifyContent="start"
                height="auto"
              >
                <Content
                  icon={SvgFileText}
                  title={t("detail.instructions.title")}
                  description={t("detail.instructions.description")}
                  sizePreset="main-ui"
                  variant="section"
                  width="full"
                />
                <InputTextArea
                  rows={4}
                  value={instructions}
                  onChange={(event) => setInstructions(event.target.value)}
                  placeholder={t("create.instructions.placeholder")}
                  autoResize
                  maxRows={12}
                />
                {instructionsDirty && (
                  <Button
                    disabled={saving}
                    onClick={() => void handleSaveInstructions()}
                  >
                    {t("detail.save.label")}
                  </Button>
                )}
              </Section>
            </Card>

            <Card border="solid" rounding={4} padding={4}>
              <Section
                gap={3}
                alignItems="stretch"
                justifyContent="start"
                height="auto"
              >
                <Content
                  icon={SvgSliders}
                  title={t("detail.details.title")}
                  description={t("detail.details.description")}
                  sizePreset="main-ui"
                  variant="section"
                  width="full"
                />
                <InputTextArea
                  rows={2}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder={t("create.description.placeholder")}
                  autoResize
                  maxRows={6}
                />
                {detailsDirty && (
                  <Button
                    disabled={saving}
                    onClick={() => void handleSaveDetails()}
                  >
                    {t("detail.save.label")}
                  </Button>
                )}
              </Section>
            </Card>
          </Section>
        )}
      </SettingsLayouts.Body>

      {pendingName && data && (
        <ConfirmationModalLayout
          icon={SvgEdit}
          title={t("rename.title", { name: pendingName })}
          description={t("rename.description")}
          onClose={renaming ? undefined : () => setPendingName(null)}
          submit={
            <Button
              disabled={renaming}
              onClick={() => void handleConfirmRename()}
            >
              {t("rename.confirm.label")}
            </Button>
          }
        />
      )}

      {deleteOpen && data && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("delete.title", { name: data.name })}
          description={t("delete.description")}
          onClose={deleting ? undefined : () => setDeleteOpen(false)}
          submit={
            <Button
              variant="danger"
              disabled={deleting}
              onClick={() => void handleDeleteProject()}
            >
              {t("delete.confirm.label")}
            </Button>
          }
        />
      )}
    </SettingsLayouts.Root>
  );
}
