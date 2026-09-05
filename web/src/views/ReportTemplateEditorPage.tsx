"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";
import {
  Button,
  InputTextArea,
  InputTypeIn,
  MessageCard,
} from "@opal/components";
import {
  Content,
  InputVertical,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import { SvgFileText, SvgSimpleLoader } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import useUnsavedChangesGuard from "@/hooks/useUnsavedChangesGuard";
import { useReportTemplate } from "@/lib/report-templates/hooks";
import {
  createReportTemplate,
  updateReportTemplate,
} from "@/lib/report-templates/api";
import { suggestReportTemplateSlug } from "@/lib/report-templates/types";
import { SWR_KEYS } from "@/lib/swr-keys";
import UnsavedChangesModal from "@/sections/modals/UnsavedChangesModal";
import { CRAFT_REPORT_TEMPLATES_PATH } from "@/app/craft/v1/constants";

function draftKey(input: {
  name: string;
  slug: string;
  description: string;
  body: string;
}): string {
  return JSON.stringify(input);
}

interface ReportTemplateEditorPageProps {
  templateId?: string;
}

export default function ReportTemplateEditorPage({
  templateId,
}: ReportTemplateEditorPageProps) {
  const t = useTranslations("craft.reportTemplates");
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const isCreating = templateId === undefined;
  const { data: template, error, isLoading } = useReportTemplate(templateId);

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [body, setBody] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [baseline, setBaseline] = useState("");
  const [hydratedId, setHydratedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isCreating && baseline === "") {
      setBaseline(
        draftKey({ name: "", slug: "", description: "", body: "" })
      );
    }
  }, [baseline, isCreating]);

  useEffect(() => {
    if (!template || template.id === hydratedId) return;
    setName(template.name);
    setSlug(template.slug);
    setDescription(template.description);
    setBody(template.body);
    setSlugTouched(true);
    setBaseline(
      draftKey({
        name: template.name,
        slug: template.slug,
        description: template.description,
        body: template.body,
      })
    );
    setHydratedId(template.id);
  }, [hydratedId, template]);

  const currentDraft = draftKey({ name, slug, description, body });
  const isDirty = baseline !== "" && currentDraft !== baseline;
  const unsavedChanges = useUnsavedChangesGuard({ isDirty });
  const fieldsLocked =
    !isCreating && template !== undefined && !template.can_edit;
  const saveBlocked =
    !name.trim() ||
    !body.trim() ||
    (isCreating && !slug.trim()) ||
    fieldsLocked;

  function leaveEditor() {
    // SAFETY: CRAFT_REPORT_TEMPLATES_PATH is the static list route.
    router.push(CRAFT_REPORT_TEMPLATES_PATH as Route);
  }

  function changeName(value: string) {
    setName(value);
    if (isCreating && !slugTouched) {
      setSlug(suggestReportTemplateSlug(value));
    }
  }

  async function handleSave() {
    if (saveBlocked) return;
    setSaving(true);
    try {
      if (isCreating) {
        const created = await createReportTemplate({
          name: name.trim(),
          slug: slug.trim(),
          description: description.trim(),
          body: body.trim(),
        });
        await mutate(SWR_KEYS.reportTemplates);
        toast.success(t("toasts.saved.message"));
        // SAFETY: created.id is the UUID of the template that was just saved.
        router.replace(
          `${CRAFT_REPORT_TEMPLATES_PATH}/edit/${created.id}` as Route
        );
      } else if (template) {
        await updateReportTemplate(template.id, {
          name: name.trim(),
          description: description.trim(),
          body: body.trim(),
        });
        await mutate(SWR_KEYS.reportTemplates);
        await mutate(SWR_KEYS.reportTemplate(template.id));
        setBaseline(draftKey({ name, slug, description, body }));
        toast.success(t("toasts.saved.message"));
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

  return (
    <SettingsLayouts.Root width="lg">
      <SettingsLayouts.Header
        icon={SvgFileText}
        title={
          name.trim() ||
          (isCreating ? t("editor.title.create") : t("editor.title.edit"))
        }
        description={
          isCreating ? t("editor.subtitle.create") : t("editor.subtitle.edit")
        }
        rightChildren={
          <div className="flex items-center gap-2">
            <Button
              prominence="secondary"
              onClick={() => unsavedChanges.requestLeave(leaveEditor)}
            >
              {t("editor.cancel.label")}
            </Button>
            <Button
              disabled={saveBlocked || saving}
              onClick={() => void handleSave()}
            >
              {saving ? t("editor.saving.label") : t("editor.save.label")}
            </Button>
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

        {(isCreating || template) && !isLoading && !error && (
          <Section gap={3} alignItems="stretch">
            {fieldsLocked && (
              <MessageCard
                variant="info"
                title={t("card.origin.workspace.label")}
                description={t("editor.readOnly.description")}
              />
            )}
            <Content
              title={t("editor.name.title")}
              sizePreset="main-content"
              variant="section"
            />
            <InputVertical withLabel="template-name" title={t("editor.name.title")}>
              <InputTypeIn
                id="template-name"
                value={name}
                maxLength={128}
                onChange={(event) => changeName(event.target.value)}
                placeholder={t("editor.name.placeholder")}
                variant={fieldsLocked ? "disabled" : "primary"}
              />
            </InputVertical>
            <InputVertical
              withLabel="template-slug"
              title={t("editor.slug.title")}
              description={t("editor.slug.hint")}
            >
              <InputTypeIn
                id="template-slug"
                value={slug}
                maxLength={64}
                onChange={(event) => {
                  setSlugTouched(true);
                  setSlug(event.target.value);
                }}
                placeholder={t("editor.slug.placeholder")}
                variant={isCreating && !fieldsLocked ? "primary" : "disabled"}
              />
            </InputVertical>
            <InputVertical
              withLabel="template-description"
              title={t("editor.description.title")}
            >
              <InputTextArea
                id="template-description"
                rows={2}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder={t("editor.description.placeholder")}
                autoResize
                maxRows={4}
                variant={fieldsLocked ? "disabled" : "primary"}
              />
            </InputVertical>
            <InputVertical withLabel="template-body" title={t("editor.body.title")}>
              <InputTextArea
                id="template-body"
                rows={16}
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder={t("editor.body.placeholder")}
                autoResize
                maxRows={40}
                variant={fieldsLocked ? "disabled" : "primary"}
              />
            </InputVertical>
          </Section>
        )}
      </SettingsLayouts.Body>

      <UnsavedChangesModal
        open={unsavedChanges.confirmationOpen}
        onCancel={unsavedChanges.cancelLeave}
        onDiscard={unsavedChanges.discardAndLeave}
      />
    </SettingsLayouts.Root>
  );
}
