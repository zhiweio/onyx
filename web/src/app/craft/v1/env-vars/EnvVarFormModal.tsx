"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Checkbox,
  InputTypeIn,
  MessageCard,
  Modal,
  PasswordInputTypeIn,
  Text,
} from "@opal/components";
import { InputVertical, toast } from "@opal/layouts";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { createEnvVar, updateEnvVar } from "@/app/craft/v1/env-vars/api";
import type { EnvVarItem } from "@/app/craft/v1/env-vars/interfaces";
import type { CraftProject } from "@/lib/craft-projects/types";

interface EnvVarFormModalProps {
  open: boolean;
  onClose: () => void;
  /** Invoked after a successful save so the caller can refresh. */
  onSaved: () => void | Promise<void>;
  /** ``null`` creates a new row; an item edits it. Scope is immutable. */
  initial: EnvVarItem | null;
  /** Projects offered as the PROJECT scope target in create mode. */
  projects: CraftProject[];
}

/**
 * Create / edit one env var or secret.
 *
 * Write-only secret semantics: an existing secret's value is never shown;
 * typing a new one overwrites it. Leaving it blank keeps the stored value.
 */
export default function EnvVarFormModal({
  open,
  onClose,
  onSaved,
  initial,
  projects,
}: EnvVarFormModalProps) {
  const t = useTranslations("craft.envVars.form");
  const isEdit = initial !== null;
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [isSecret, setIsSecret] = useState(false);
  // "user" or a project id.
  const [scopeSelection, setScopeSelection] = useState<string>("user");
  const [saving, setSaving] = useState(false);

  // Re-seed each open so a prior attempt doesn't leak in.
  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setValue("");
    setIsSecret(initial?.is_secret ?? false);
    setScopeSelection(initial?.project_id ?? "user");
  }, [open, initial]);

  const trimmedName = name.trim();
  const trimmedValue = value.trim();
  const nameError = trimmedName ? null : t("errors.nameRequired");
  const valueError = trimmedValue || isEdit ? null : t("errors.valueRequired");
  const canSave = !nameError && !valueError && !saving;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    try {
      if (isEdit && initial) {
        await updateEnvVar(initial.id, {
          name: trimmedName,
          // Blank value on edit = keep the stored one (secrets are
          // write-only, so there is nothing to echo back).
          ...(trimmedValue ? { value: trimmedValue } : {}),
        });
        toast.success(t("toasts.updated"));
      } else {
        await createEnvVar({
          name: trimmedName,
          value: trimmedValue,
          is_secret: isSecret,
          scope: scopeSelection === "user" ? "USER" : "PROJECT",
          ...(scopeSelection !== "user" ? { project_id: scopeSelection } : {}),
        });
        toast.success(t("toasts.created"));
      }
      onClose();
      await onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("toasts.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={saving ? undefined : onClose}>
      <div className="flex w-full flex-col gap-4 p-6">
        <Text font="main-ui-heading">
          {isEdit ? t("editTitle") : t("createTitle")}
        </Text>

        <InputVertical withLabel title={t("fields.name.label")}>
          <InputTypeIn
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("fields.name.placeholder")}
            data-testid="env-var-name-input"
          />
        </InputVertical>

        <InputVertical
          withLabel
          title={
            isSecret ? t("fields.secretValue.label") : t("fields.value.label")
          }
          description={
            isEdit && isSecret ? t("fields.secretValue.keepHint") : undefined
          }
        >
          {isSecret ? (
            <PasswordInputTypeIn
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={
                isEdit
                  ? t("fields.secretValue.overwritePlaceholder")
                  : t("fields.secretValue.placeholder")
              }
              data-testid="env-var-value-input"
            />
          ) : (
            <InputTypeIn
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={t("fields.value.placeholder")}
              data-testid="env-var-value-input"
            />
          )}
        </InputVertical>

        {!isEdit && (
          <>
            <InputVertical withLabel title={t("fields.isSecret.label")}>
              <label
                className="flex cursor-pointer items-center gap-2"
                htmlFor="env-var-is-secret"
              >
                <Checkbox
                  id="env-var-is-secret"
                  checked={isSecret}
                  onCheckedChange={() => setIsSecret((prev) => !prev)}
                />
                <Text font="secondary-body">
                  {t("fields.isSecret.description")}
                </Text>
              </label>
            </InputVertical>

            <InputVertical withLabel title={t("fields.scope.label")}>
              <InputSelect
                value={scopeSelection}
                onValueChange={setScopeSelection}
              >
                <InputSelect.Trigger />
                <InputSelect.Content>
                  <InputSelect.Item value="user">
                    {t("fields.scope.user")}
                  </InputSelect.Item>
                  {projects.map((project) => (
                    <InputSelect.Item key={project.id} value={project.id}>
                      {project.name}
                    </InputSelect.Item>
                  ))}
                </InputSelect.Content>
              </InputSelect>
            </InputVertical>
          </>
        )}

        {(nameError || valueError) && (
          <MessageCard
            variant="error"
            title={t("errors.title")}
            description={nameError ?? valueError ?? ""}
          />
        )}

        <div className="flex justify-end gap-2">
          <Button
            variant="default"
            prominence="secondary"
            disabled={saving}
            onClick={onClose}
          >
            {t("cancelButton")}
          </Button>
          <Button
            variant="default"
            prominence="primary"
            disabled={!canSave}
            onClick={() => void handleSave()}
            data-testid="env-var-save"
          >
            {isEdit ? t("saveChangesButton") : t("createButton")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
