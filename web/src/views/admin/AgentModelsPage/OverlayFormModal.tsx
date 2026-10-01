"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  BasicModalFooter,
  Button,
  InputSelect,
  InputTypeIn,
  MessageCard,
  Modal,
  Text,
} from "@opal/components";
import { InputVertical, toast } from "@opal/layouts";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import {
  createAgentModelOverlay,
  type AgentModelView,
  type OverlayCreateBody,
} from "./api";

interface OverlayFormModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
  /** Catalog models offered as the overlay template. */
  catalog: AgentModelView[];
}

interface OverlayDraft {
  name: string;
  provider: string;
  template_model_id: string;
  model_id: string;
  base_url: string;
  context_window: string;
  max_output_tokens: string;
}

const EMPTY_DRAFT: OverlayDraft = {
  name: "",
  provider: "",
  template_model_id: "",
  model_id: "",
  base_url: "",
  context_window: "",
  max_output_tokens: "",
};

export default function OverlayFormModal({
  open,
  onClose,
  onSaved,
  catalog,
}: OverlayFormModalProps) {
  const t = useTranslations("admin.agentModels");
  const [draft, setDraft] = useState<OverlayDraft>(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(EMPTY_DRAFT);
    setSubmitAttempted(false);
    nameInputRef.current?.focus();
  }, [open]);

  const nameError = draft.name.trim() ? null : t("form.errors.nameRequired");
  const providerError = draft.provider.trim()
    ? null
    : t("form.errors.providerRequired");
  const templateError = draft.template_model_id
    ? null
    : t("form.errors.templateRequired");
  const canSave = !nameError && !providerError && !templateError && !saving;

  async function handleSave() {
    setSubmitAttempted(true);
    if (!canSave) return;
    setSaving(true);
    try {
      const body: OverlayCreateBody = {
        name: draft.name.trim(),
        provider: draft.provider.trim(),
        template_model_id: draft.template_model_id,
      };
      if (draft.model_id.trim()) body.model_id = draft.model_id.trim();
      if (draft.base_url.trim()) body.base_url = draft.base_url.trim();
      if (draft.context_window.trim()) {
        body.context_window = Number(draft.context_window);
      }
      if (draft.max_output_tokens.trim()) {
        body.max_output_tokens = Number(draft.max_output_tokens);
      }
      await createAgentModelOverlay(body);
      toast.success(t("created"));
      onClose();
      await onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next && !saving) onClose();
      }}
    >
      <Modal.Content width="md">
        <Modal.Header
          icon={ADMIN_ROUTES.LLM_MODELS.icon}
          title={t("form.title")}
          description={t("form.description")}
          onClose={() => {
            if (!saving) onClose();
          }}
        />
        <Modal.Body>
          <form
            id="agent-model-overlay-form"
            className="flex w-full flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSave();
            }}
          >
            <InputVertical withLabel title={t("form.name")}>
              <InputTypeIn
                ref={nameInputRef}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder={t("form.namePlaceholder")}
                data-testid="agent-model-name-input"
              />
            </InputVertical>

            <InputVertical withLabel title={t("form.provider")}>
              <InputTypeIn
                value={draft.provider}
                onChange={(e) =>
                  setDraft({ ...draft, provider: e.target.value })
                }
                placeholder={t("form.providerPlaceholder")}
                data-testid="agent-model-provider-input"
              />
            </InputVertical>

            <InputVertical
              withLabel
              title={t("form.template")}
              description={t("form.templateDescription")}
            >
              <InputSelect
                value={draft.template_model_id}
                onValueChange={(value) =>
                  setDraft({ ...draft, template_model_id: value })
                }
              >
                <InputSelect.Trigger
                  placeholder={t("form.templatePlaceholder")}
                />
                <InputSelect.Content>
                  {catalog.map((model) => (
                    <InputSelect.Item
                      key={model.model_id}
                      value={model.model_id}
                    >
                      {model.display_name}
                    </InputSelect.Item>
                  ))}
                </InputSelect.Content>
              </InputSelect>
            </InputVertical>

            <InputVertical
              withLabel
              title={t("form.modelId")}
              description={t("form.modelIdDescription")}
            >
              <InputTypeIn
                value={draft.model_id}
                onChange={(e) =>
                  setDraft({ ...draft, model_id: e.target.value })
                }
                placeholder={t("form.modelIdPlaceholder")}
                data-testid="agent-model-id-input"
              />
            </InputVertical>

            <InputVertical withLabel title={t("form.baseUrl")}>
              <InputTypeIn
                value={draft.base_url}
                onChange={(e) =>
                  setDraft({ ...draft, base_url: e.target.value })
                }
                placeholder={t("form.baseUrlPlaceholder")}
                data-testid="agent-model-base-url-input"
              />
            </InputVertical>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <InputVertical withLabel title={t("form.context")}>
                <InputTypeIn
                  inputMode="numeric"
                  value={draft.context_window}
                  onChange={(e) =>
                    setDraft({ ...draft, context_window: e.target.value })
                  }
                  placeholder={t("form.contextPlaceholder")}
                  data-testid="agent-model-context-input"
                />
              </InputVertical>
              <InputVertical withLabel title={t("form.maxOutput")}>
                <InputTypeIn
                  inputMode="numeric"
                  value={draft.max_output_tokens}
                  onChange={(e) =>
                    setDraft({ ...draft, max_output_tokens: e.target.value })
                  }
                  placeholder={t("form.maxOutputPlaceholder")}
                  data-testid="agent-model-max-output-input"
                />
              </InputVertical>
            </div>

            {submitAttempted &&
              (nameError || providerError || templateError) && (
                <MessageCard
                  variant="error"
                  title={t("form.errors.title")}
                  description={
                    nameError ?? providerError ?? templateError ?? ""
                  }
                />
              )}
            <Text as="p" font="secondary-body" color="text-03">
              {t("form.hint")}
            </Text>
          </form>
        </Modal.Body>
        <Modal.Footer>
          <BasicModalFooter
            cancel={
              <Button
                prominence="secondary"
                type="button"
                disabled={saving}
                onClick={onClose}
              >
                {t("form.cancel")}
              </Button>
            }
            submit={
              <Button
                type="submit"
                form="agent-model-overlay-form"
                disabled={!canSave}
                data-testid="agent-model-save"
              >
                {t("form.submit")}
              </Button>
            }
          />
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
