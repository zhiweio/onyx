"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button, InputTextArea, Tag } from "@opal/components";
import { ConfirmationModalLayout, InputVertical } from "@opal/layouts";
import { SvgUploadCloud } from "@opal/icons";
import ScenarioComposer from "@/sections/scenarios/editor/ScenarioComposer";
import { useCatalogScenarioEditor } from "@/lib/scenarios/hooks";
import {
  publishCatalogEntry,
  unpublishCatalogEntry,
} from "@/lib/system-catalog/api";
import {
  publishStatusMessageKey,
  publishStatusTagColor,
} from "@/lib/system-catalog/types";
import UnsavedChangesModal from "@/sections/modals/UnsavedChangesModal";
import { toast } from "@opal/layouts";

interface CatalogScenarioEditorPageProps {
  entryId?: string;
}

export default function CatalogScenarioEditorPage({
  entryId,
}: CatalogScenarioEditorPageProps) {
  const t = useTranslations("craft.scenarioEditor");
  const tCatalog = useTranslations("admin.craftCatalog");
  const editor = useCatalogScenarioEditor(entryId);
  const [publishOpen, setPublishOpen] = useState(false);
  const [changelog, setChangelog] = useState("");
  const [pending, setPending] = useState(false);

  const item = editor.item;
  const published = item?.publish_status === "PUBLISHED";

  async function handlePublish() {
    if (!item) return;
    setPending(true);
    try {
      await publishCatalogEntry("scenarios", item.id, changelog);
      await editor.refresh();
      toast.success(tCatalog("toasts.published.message", { name: item.name }));
      setPublishOpen(false);
      setChangelog("");
    } catch (error) {
      console.error(error);
      toast.error(
        error instanceof Error
          ? error.message
          : tCatalog("toasts.actionFailed.message")
      );
    } finally {
      setPending(false);
    }
  }

  async function handleUnpublish() {
    if (!item) return;
    setPending(true);
    try {
      await unpublishCatalogEntry("scenarios", item.id);
      await editor.refresh();
      toast.success(
        tCatalog("toasts.unpublished.message", { name: item.name })
      );
    } catch (error) {
      console.error(error);
      toast.error(
        error instanceof Error
          ? error.message
          : tCatalog("toasts.actionFailed.message")
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="h-full min-w-0 w-full">
      <ScenarioComposer
        mode={editor.mode}
        isCreating={editor.isCreating}
        isLoading={editor.isLoading}
        error={editor.error}
        canEdit={editor.canEdit}
        fieldsLocked={editor.fieldsLocked || pending}
        draft={editor.draft}
        conditionals={editor.conditionals}
        onDraftChange={editor.onDraftChange}
        onConditionalsChange={editor.onConditionalsChange}
        skillCatalog={editor.skillCatalog}
        templates={editor.templates}
        isDirty={editor.isDirty}
        statusTags={
          item ? (
            <div className="flex flex-wrap items-center gap-1">
              <Tag
                size="sm"
                color={publishStatusTagColor(item.publish_status)}
                title={tCatalog(publishStatusMessageKey(item.publish_status))}
              />
              <Tag
                size="sm"
                color="gray"
                title={t("status.version.label", { version: item.version })}
              />
            </div>
          ) : undefined
        }
        onCancel={editor.onCancel}
        onSave={editor.onSave}
        saving={editor.saving}
        canSave={editor.canSave}
        saveTooltip={editor.saveTooltip}
        onPublish={item ? () => setPublishOpen(true) : undefined}
        onUnpublish={published ? () => void handleUnpublish() : undefined}
      />
      <UnsavedChangesModal
        open={editor.unsavedChanges.confirmationOpen}
        onCancel={editor.unsavedChanges.cancelLeave}
        onDiscard={editor.unsavedChanges.discardAndLeave}
      />
      {publishOpen && item && (
        <ConfirmationModalLayout
          icon={SvgUploadCloud}
          title={tCatalog("publish.title", { name: item.name })}
          description={tCatalog("publish.description")}
          onClose={pending ? undefined : () => setPublishOpen(false)}
          submit={
            <Button disabled={pending} onClick={() => void handlePublish()}>
              {tCatalog("publish.confirm.label")}
            </Button>
          }
        >
          <InputVertical withLabel title={tCatalog("publish.changelog.label")}>
            <InputTextArea
              value={changelog}
              onChange={(event) => setChangelog(event.target.value)}
              placeholder={tCatalog("publish.changelog.placeholder")}
            />
          </InputVertical>
        </ConfirmationModalLayout>
      )}
    </div>
  );
}
