"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Checkbox, InputTypeIn, Modal, Text } from "@opal/components";
import { SvgSliders } from "@opal/icons";
import { InputHorizontal, InputVertical, Section } from "@opal/layouts";
import { Disabled } from "@opal/core";
import type {
  LLMModality,
  ModelConfiguration,
} from "@/lib/languageModels/types";
import { modelDisplayName } from "@/lib/languageModels/utils";

const INPUT_TYPE_OPTIONS: Exclude<LLMModality, "text">[] = [
  "image",
  "video",
  "pdf",
];

export type ModelSettingsPatch = Partial<
  Pick<
    ModelConfiguration,
    | "name"
    | "max_input_tokens"
    | "max_output_tokens"
    | "input_modalities"
    | "output_modalities"
    | "supports_image_input"
    | "reasoning_effort_max"
    | "reasoning_effort_default"
    | "temperature_default"
  >
>;

export type ModelSettingsModel = Pick<
  ModelConfiguration,
  | "name"
  | "display_name"
  | "custom_display_name"
  | "vendor"
  | "max_input_tokens"
  | "max_output_tokens"
  | "input_modalities"
  | "output_modalities"
  | "supports_reasoning"
  | "supports_image_input"
  | "supported_reasoning_efforts"
  | "reasoning_effort_max"
  | "reasoning_effort_default"
  | "temperature_default"
>;

interface ModelSettingsPopoverProps {
  model: ModelSettingsModel;
  onChange: (patch: ModelSettingsPatch) => void;
  onOpenChange?: (open: boolean) => void;
  canEditModelId?: boolean;
}

function parseTokenField(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function resolvedInputModalities(model: ModelSettingsModel): LLMModality[] {
  if (model.input_modalities && model.input_modalities.length > 0) {
    return model.input_modalities;
  }
  return model.supports_image_input ? ["text", "image"] : ["text"];
}

function TypeOption({
  label,
  checked,
  disabled,
  tooltip,
  onCheckedChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  tooltip?: string;
  onCheckedChange?: (checked: boolean) => void;
}) {
  const option = (
    <Section
      flexDirection="row"
      alignItems="center"
      width="fit"
      height="auto"
      gap={1}
    >
      <Checkbox
        checked={checked}
        aria-label={label}
        onCheckedChange={onCheckedChange}
      />
      <Text font="main-ui-body">{label}</Text>
    </Section>
  );

  if (!disabled) return option;

  return (
    <Disabled disabled tooltip={tooltip}>
      {option}
    </Disabled>
  );
}

export function ModelSettingsPopover({
  model,
  onChange,
  onOpenChange,
  canEditModelId = false,
}: ModelSettingsPopoverProps) {
  const t = useTranslations("admin.languageModels.modals");
  const [open, setOpen] = useState(false);
  function handleOpenChange(next: boolean) {
    setOpen(next);
    onOpenChange?.(next);
  }

  const inputModalities = resolvedInputModalities(model);

  function toggleInputType(
    type: Exclude<LLMModality, "text">,
    checked: boolean
  ) {
    const next = new Set(inputModalities);
    next.add("text");
    if (checked) next.add(type);
    else next.delete(type);
    const modalities = Array.from(next);
    onChange({
      input_modalities: modalities,
      supports_image_input: modalities.includes("image"),
    });
  }

  return (
    <>
      <Button
        icon={SvgSliders}
        prominence="internal"
        size="sm"
        tooltip={t("modelSettings.trigger.tooltip")}
        aria-label={t("modelSettings.trigger.tooltip")}
        onClick={(e: React.MouseEvent) => {
          e.stopPropagation();
          handleOpenChange(true);
        }}
      />
      <Modal open={open} onOpenChange={handleOpenChange}>
        <Modal.Content width="sm">
          <Modal.Header
            icon={SvgSliders}
            title={t("modelSettings.dialog.title")}
            description={modelDisplayName(model)}
            onClose={() => handleOpenChange(false)}
          />
          <Modal.Body>
            <Section alignItems="stretch" height="auto" gap={3}>
              <InputVertical
                title={t("modelSettings.modelId.title")}
                subDescription={t("modelSettings.modelId.description")}
              >
                <InputTypeIn
                  value={model.name}
                  disabled={!canEditModelId}
                  onChange={(e) => onChange({ name: e.target.value })}
                />
              </InputVertical>
              <InputVertical
                title={t("modelSettings.contextWindow.title")}
                subDescription={t("modelSettings.contextWindow.description")}
              >
                <InputTypeIn
                  type="number"
                  value={model.max_input_tokens?.toString() ?? ""}
                  placeholder={t("modelSettings.contextWindow.placeholder")}
                  onChange={(e) =>
                    onChange({ max_input_tokens: parseTokenField(e.target.value) })
                  }
                />
              </InputVertical>
              <InputVertical
                title={t("modelSettings.maxOutputTokens.title")}
                subDescription={t("modelSettings.maxOutputTokens.description")}
              >
                <InputTypeIn
                  type="number"
                  value={model.max_output_tokens?.toString() ?? ""}
                  placeholder={t("modelSettings.maxOutputTokens.placeholder")}
                  onChange={(e) =>
                    onChange({
                      max_output_tokens: parseTokenField(e.target.value),
                    })
                  }
                />
              </InputVertical>
              <InputHorizontal
                title={t("modelSettings.inputTypes.title")}
                description={t("modelSettings.inputTypes.description")}
              >
                <Section
                  flexDirection="row"
                  alignItems="center"
                  width="fit"
                  height="auto"
                  gap={3}
                >
                  <TypeOption
                    label={t("modelSettings.types.text.label")}
                    checked
                    disabled
                    tooltip={t("modelSettings.inputTypes.textLocked.tooltip")}
                  />
                  {INPUT_TYPE_OPTIONS.map((type) => (
                    <TypeOption
                      key={type}
                      label={t(`modelSettings.types.${type}.label`)}
                      checked={inputModalities.includes(type)}
                      onCheckedChange={(checked) =>
                        toggleInputType(type, checked)
                      }
                    />
                  ))}
                </Section>
              </InputHorizontal>
              <InputHorizontal
                title={t("modelSettings.outputTypes.title")}
                description={t("modelSettings.outputTypes.description")}
              >
                <TypeOption
                  label={t("modelSettings.types.text.label")}
                  checked
                  disabled
                  tooltip={t("modelSettings.outputTypes.textLocked.tooltip")}
                />
              </InputHorizontal>
            </Section>
          </Modal.Body>
        </Modal.Content>
      </Modal>
    </>
  );
}
