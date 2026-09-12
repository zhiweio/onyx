"use client";

import ScenarioComposer from "@/sections/scenarios/editor/ScenarioComposer";
import { useUserScenarioEditor } from "@/lib/scenarios/hooks";
import ShareScenarioModal from "@/sections/modals/scenarios/ShareScenarioModal";
import UnsavedChangesModal from "@/sections/modals/UnsavedChangesModal";

interface ScenarioEditorPageProps {
  scenarioId?: string;
}

export default function ScenarioEditorPage({
  scenarioId,
}: ScenarioEditorPageProps) {
  const editor = useUserScenarioEditor(scenarioId);

  return (
    <div className="h-full min-w-0 w-full">
      <ScenarioComposer
        mode={editor.mode}
        isCreating={editor.isCreating}
        isLoading={editor.isLoading}
        error={editor.error}
        canEdit={editor.canEdit}
        fieldsLocked={editor.fieldsLocked}
        draft={editor.draft}
        conditionals={editor.conditionals}
        onDraftChange={editor.onDraftChange}
        onConditionalsChange={editor.onConditionalsChange}
        skillCatalog={editor.skillCatalog}
        templates={editor.templates}
        knownCustomDomains={editor.knownCustomDomains}
        isDirty={editor.isDirty}
        onCancel={editor.onCancel}
        onSave={editor.onSave}
        saving={editor.saving}
        canSave={editor.canSave}
        saveTooltip={editor.saveTooltip}
        onShare={editor.onShare}
        onStartRun={editor.onStartRun}
        starting={editor.starting}
        onCustomize={editor.onCustomize}
        customizing={editor.customizing}
      />
      <ShareScenarioModal
        scenario={editor.scenario ?? null}
        open={editor.shareOpen}
        onClose={() => editor.setShareOpen(false)}
        onSaved={() => {
          void editor.refresh();
        }}
      />
      <UnsavedChangesModal
        open={editor.unsavedChanges.confirmationOpen}
        onCancel={editor.unsavedChanges.cancelLeave}
        onDiscard={editor.unsavedChanges.discardAndLeave}
      />
    </div>
  );
}
