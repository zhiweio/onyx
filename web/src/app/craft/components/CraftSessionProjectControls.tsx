"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, InputTypeIn, LineItemButton, Text } from "@opal/components";
import { ConfirmationModalLayout, toast } from "@opal/layouts";
import { SvgFolder, SvgPlus, SvgTrash } from "@opal/icons";
import { noProp } from "@/lib/utils";
import { createCraftProject } from "@/lib/craft-projects/api";
import { isImplicitUntitledProject } from "@/lib/craft-projects/display";
import type { CraftProject } from "@/lib/craft-projects/types";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

interface UseCraftSessionProjectControlsArgs {
  sessionId: string;
  projectId: string | null;
  sessionTitle: string;
  projects: CraftProject[];
  onProjectsChanged?: () => Promise<void> | void;
}

export function useCraftSessionProjectControls({
  sessionId,
  projectId,
  sessionTitle,
  projects,
  onProjectsChanged,
}: UseCraftSessionProjectControlsArgs) {
  const t = useTranslations("craft.sideBar");
  const assignBuildSessionProject = useBuildSessionStore(
    (state) => state.assignBuildSessionProject
  );
  const [picking, setPicking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [busy, setBusy] = useState(false);

  const visibleProjects = projects.filter(
    (project) => !isImplicitUntitledProject(project)
  );

  const handleAssign = useCallback(
    async (nextProjectId: string | null) => {
      setBusy(true);
      try {
        await assignBuildSessionProject(sessionId, nextProjectId);
        if (nextProjectId) {
          const name =
            visibleProjects.find((project) => project.id === nextProjectId)
              ?.name ?? "";
          toast.success(t("toast.movedToProject", { title: name }));
        } else {
          toast.success(t("toast.removedFromProject"));
        }
        await onProjectsChanged?.();
        setPicking(false);
      } catch (error) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("toast.moveProjectFailed")
        );
      } finally {
        setBusy(false);
      }
    },
    [assignBuildSessionProject, onProjectsChanged, sessionId, t, visibleProjects]
  );

  const handleSaveAs = useCallback(async () => {
    const name = saveName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const created = await createCraftProject({
        name,
        description: "",
        instructions: null,
      });
      await assignBuildSessionProject(sessionId, created.id);
      toast.success(t("toast.movedToProject", { title: created.name }));
      setSaving(false);
      setSaveName("");
      await onProjectsChanged?.();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("toast.saveAsProjectFailed")
      );
    } finally {
      setBusy(false);
    }
  }, [
    assignBuildSessionProject,
    onProjectsChanged,
    saveName,
    sessionId,
    t,
  ]);

  const menuItems = picking
    ? [
        ...visibleProjects.map((project) => (
          <LineItemButton
            key={project.id}
            sizePreset="main-ui"
            rounding={2}
            icon={SvgFolder}
            disabled={busy || project.id === projectId}
            onClick={noProp(() => void handleAssign(project.id))}
            title={project.name}
          />
        )),
        <LineItemButton
          key="cancel-pick"
          sizePreset="main-ui"
          rounding={2}
          disabled={busy}
          onClick={noProp(() => setPicking(false))}
          title={t("sessionProject.cancel.label")}
        />,
      ]
    : [
        <LineItemButton
          key="save-as"
          sizePreset="main-ui"
          rounding={2}
          icon={SvgPlus}
          disabled={busy}
          onClick={noProp(() => {
            setSaveName(sessionTitle.trim() || "");
            setSaving(true);
          })}
          title={t("sessionProject.saveAs.label")}
        />,
        <LineItemButton
          key="move"
          sizePreset="main-ui"
          rounding={2}
          icon={SvgFolder}
          disabled={busy || visibleProjects.length === 0}
          onClick={noProp(() => setPicking(true))}
          title={
            projectId
              ? t("sessionProject.move.label")
              : t("sessionProject.add.label")
          }
        />,
        projectId ? (
          <LineItemButton
            key="remove"
            sizePreset="main-ui"
            rounding={2}
            icon={SvgTrash}
            disabled={busy}
            onClick={noProp(() => void handleAssign(null))}
            title={t("sessionProject.remove.label")}
          />
        ) : null,
      ];

  return {
    picking,
    menuItems,
    modal: saving ? (
      <ConfirmationModalLayout
        title={t("sessionProject.saveAs.title")}
        icon={SvgFolder}
        onClose={busy ? undefined : () => setSaving(false)}
        submit={
          <Button
            disabled={busy || !saveName.trim()}
            prominence="primary"
            onClick={() => void handleSaveAs()}
          >
            {t("sessionProject.saveAs.submit")}
          </Button>
        }
      >
        <InputTypeIn
          value={saveName}
          onChange={(event) => setSaveName(event.target.value)}
          placeholder={t("sessionProject.saveAs.namePlaceholder")}
        />
        <Text font="secondary-body" color="text-03">
          {t("sessionProject.saveAs.body")}
        </Text>
      </ConfirmationModalLayout>
    ) : null,
  };
}
