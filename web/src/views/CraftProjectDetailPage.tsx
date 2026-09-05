"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { useDropzone } from "react-dropzone";
import {
  Button,
  Card,
  Divider,
  InputTextArea,
  InputTypeIn,
  LineItemButton,
  MessageCard,
  Text,
} from "@opal/components";
import {
  ConfirmationModalLayout,
  Content,
  ContentAction,
  InputVertical,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import {
  SvgDownload,
  SvgFileText,
  SvgFolder,
  SvgPlayCircle,
  SvgSimpleLoader,
  SvgTrash,
  SvgUploadCloud,
} from "@opal/icons";
import { cn } from "@opal/utils";
import { Section } from "@/layouts/general-layouts";
import { useCraftProject } from "@/lib/craft-projects/hooks";
import {
  craftProjectFileUrl,
  deleteCraftProject,
  deleteCraftProjectFile,
  startCraftProjectSession,
  updateCraftProject,
  uploadCraftProjectFile,
} from "@/lib/craft-projects/api";
import type {
  CraftProjectFile,
  CraftProjectSession,
} from "@/lib/craft-projects/types";
import {
  CRAFT_PATH,
  CRAFT_PROJECTS_PATH,
} from "@/app/craft/v1/constants";
import { CRAFT_SEARCH_PARAM_NAMES } from "@/app/craft/services/searchParams";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

interface CraftProjectDetailPageProps {
  projectId: string;
}

export default function CraftProjectDetailPage({
  projectId,
}: CraftProjectDetailPageProps) {
  const t = useTranslations("craft.projects");
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
  const [uploading, setUploading] = useState(false);
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

  const onDrop = useCallback(
    async (files: File[]) => {
      const file = files[0];
      if (!file || !data) return;
      setUploading(true);
      try {
        await uploadCraftProjectFile(data.id, file);
        await refresh();
        toast.success(t("toasts.uploaded.message"));
      } catch (uploadError) {
        console.error(uploadError);
        toast.error(
          uploadError instanceof Error
            ? uploadError.message
            : t("toasts.uploadFailed.message")
        );
      } finally {
        setUploading(false);
      }
    },
    [data, refresh, t]
  );

  const { getRootProps, getInputProps, open, isDragActive } = useDropzone({
    disabled: uploading || isLoading,
    multiple: false,
    noClick: true,
    noKeyboard: true,
    onDropAccepted: onDrop,
  });

  async function handleRemoveFile(file: CraftProjectFile) {
    if (!data) return;
    try {
      await deleteCraftProjectFile(data.id, file.id);
      await refresh();
      toast.success(t("toasts.fileDeleted.message"));
    } catch (removeError) {
      console.error(removeError);
      toast.error(
        removeError instanceof Error
          ? removeError.message
          : t("toasts.deleteFailed.message")
      );
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

  const files = data?.files ?? [];
  const sessions = data?.sessions ?? [];
  const hasSessions = sessions.length > 0;
  const startLabel = hasSessions
    ? t("detail.newChat.label")
    : t("detail.startChat.label");

  return (
    <SettingsLayouts.Root data-testid="CraftProjectDetailPage/container">
      <SettingsLayouts.Header
        icon={SvgFolder}
        title={data?.name ?? t("page.title.text")}
        description={data?.description || undefined}
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
          <Section gap={4}>
            <Card border="solid" rounding={4} padding={4}>
              <Section gap={3}>
                <ContentAction
                  icon={SvgFolder}
                  title={t("detail.files.title")}
                  description={t("card.fileCount.label", {
                    count: files.length,
                  })}
                  sizePreset="main-ui"
                  variant="section"
                  rightChildren={
                    <Button
                      prominence="secondary"
                      icon={SvgUploadCloud}
                      disabled={uploading}
                      onClick={open}
                    >
                      {t("detail.upload.label")}
                    </Button>
                  }
                />
                <div
                  {...getRootProps()}
                  className={cn(
                    "rounded-12 p-2 flex flex-col gap-2",
                    isDragActive
                      ? "border border-dashed border-border-03 bg-background-tint-02"
                      : files.length === 0
                        ? "bg-background-tint-00"
                        : "border border-border-01"
                  )}
                >
                  <input {...getInputProps()} />
                  {files.length === 0 ? (
                    <Text font="secondary-body" color="text-03">
                      {isDragActive
                        ? t("detail.dropHint.description")
                        : t("detail.emptyFiles.description")}
                    </Text>
                  ) : (
                    <div className="flex flex-col gap-1">
                      {files.map((file) => (
                        <ContentAction
                          key={file.id}
                          icon={SvgFileText}
                          title={file.name}
                          description={
                            file.source === "session_output"
                              ? t("detail.sourceOutput.label")
                              : t("detail.sourceUpload.label")
                          }
                          sizePreset="main-ui"
                          variant="section"
                          rightChildren={
                            <div className="flex items-center gap-1">
                              <Button
                                prominence="tertiary"
                                size="sm"
                                icon={SvgDownload}
                                tooltip={t("detail.download.tooltip")}
                                aria-label={t("detail.download.tooltip")}
                                href={craftProjectFileUrl(data.id, file.id)}
                              />
                              <Button
                                prominence="tertiary"
                                size="sm"
                                icon={SvgTrash}
                                tooltip={t("detail.removeFile.tooltip")}
                                aria-label={t("detail.removeFile.tooltip")}
                                onClick={() => void handleRemoveFile(file)}
                              />
                            </div>
                          }
                        />
                      ))}
                    </div>
                  )}
                </div>
              </Section>
            </Card>

            <Card border="solid" rounding={4} padding={4}>
              <Section gap={2}>
                <Content
                  icon={SvgPlayCircle}
                  title={t("detail.sessions.title")}
                  description={t("card.sessionCount.label", {
                    count: sessions.length,
                  })}
                  sizePreset="main-ui"
                  variant="section"
                />
                {hasSessions ? (
                  <div className="flex flex-col gap-1">
                    {sessions.map((session) => (
                      <LineItemButton
                        key={session.id}
                        sizePreset="main-ui"
                        variant="section"
                        rounding={2}
                        icon={SvgPlayCircle}
                        title={session.name || session.id.slice(0, 8)}
                        description={session.status}
                        onClick={() => openSession(session)}
                      />
                    ))}
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
              defaultOpen
              title={t("detail.instructions.title")}
            >
              <Section gap={2}>
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
              <Section gap={3}>
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
