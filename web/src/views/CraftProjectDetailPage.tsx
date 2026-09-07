"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useFormatter, useTranslations } from "next-intl";
import {
  Button,
  Card,
  Divider,
  InputTextArea,
  InputTypeIn,
  LineItemButton,
  MessageCard,
  Text,
  type TagColor,
} from "@opal/components";
import {
  ConfirmationModalLayout,
  Content,
  InputVertical,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import {
  SvgFolder,
  SvgPlayCircle,
  SvgSimpleLoader,
  SvgTrash,
} from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import CraftProjectFiles from "@/app/craft/components/CraftProjectFiles";
import { useCraftProject } from "@/lib/craft-projects/hooks";
import {
  deleteCraftProject,
  startCraftProjectSession,
  updateCraftProject,
} from "@/lib/craft-projects/api";
import type { CraftProjectSession } from "@/lib/craft-projects/types";
import {
  compareProjectSessions,
  isKnownSessionRole,
  normalizeSessionStatus,
  parseSessionLane,
  projectHeadline,
} from "@/lib/craft-projects/display";
import {
  CRAFT_PATH,
  CRAFT_PROJECTS_PATH,
} from "@/app/craft/v1/constants";
import { CRAFT_SEARCH_PARAM_NAMES } from "@/app/craft/services/searchParams";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

const SESSION_STATUS_COLOR: Record<
  ReturnType<typeof normalizeSessionStatus>,
  TagColor
> = {
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
  const refreshSessionHistory = useBuildSessionStore(
    (state) => state.refreshSessionHistory
  );
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!data) return;
    setName(data.name);
    setDescription(data.description);
    setInstructions(data.instructions ?? "");
  }, [data]);

  const detailsDirty =
    data !== undefined &&
    (name.trim() !== data.name || description.trim() !== data.description);
  const instructionsDirty =
    data !== undefined &&
    (instructions.trim() || null) !== (data.instructions ?? null);

  async function handleSave() {
    if (!data || !name.trim()) return;
    setSaving(true);
    try {
      await updateCraftProject(data.id, {
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim() || null,
      });
      await refresh();
      toast.success(t("toasts.saved.message"));
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
    const items = [...(data?.sessions ?? [])];
    items.sort(compareProjectSessions);
    return items;
  }, [data?.sessions]);

  const hasSessions = sessions.length > 0;
  const startLabel = hasSessions
    ? t("detail.newChat.label")
    : t("detail.startChat.label");
  const headline = projectHeadline(data?.name ?? t("page.title.text"));
  const headerDescription = (
    data?.description?.trim() ||
    (headline.title !== headline.full ? headline.full : "")
  ).trim();

  return (
    <SettingsLayouts.Root
      width="lg"
      data-testid="CraftProjectDetailPage/container"
    >
      <SettingsLayouts.Header
        icon={SvgFolder}
        title={headline.title}
        description={headerDescription || undefined}
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
                      const statusKey = normalizeSessionStatus(session.status);
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

            <Divider
              foldable
              defaultOpen={Boolean(data.instructions)}
              title={t("detail.instructions.title")}
            >
              <Section
                gap={2}
                alignItems="stretch"
                justifyContent="start"
                height="auto"
              >
                <InputTextArea
                  rows={5}
                  value={instructions}
                  onChange={(event) => setInstructions(event.target.value)}
                  placeholder={t("create.instructions.placeholder")}
                  autoResize
                  maxRows={12}
                />
                {instructionsDirty && (
                  <Button
                    disabled={saving || !name.trim()}
                    onClick={() => void handleSave()}
                  >
                    {t("detail.save.label")}
                  </Button>
                )}
              </Section>
            </Divider>

            <Divider foldable title={t("detail.details.title")}>
              <Section
                gap={3}
                alignItems="stretch"
                justifyContent="start"
                height="auto"
              >
                <InputVertical title={t("create.name.label")} withLabel>
                  <InputTypeIn
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                  />
                </InputVertical>
                <InputVertical
                  title={t("create.description.label")}
                  withLabel
                >
                  <InputTypeIn
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder={t("create.description.placeholder")}
                  />
                </InputVertical>
                {detailsDirty && (
                  <Button
                    disabled={saving || !name.trim()}
                    onClick={() => void handleSave()}
                  >
                    {t("detail.save.label")}
                  </Button>
                )}
              </Section>
            </Divider>
          </Section>
        )}
      </SettingsLayouts.Body>

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
