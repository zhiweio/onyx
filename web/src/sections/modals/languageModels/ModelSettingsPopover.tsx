"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Checkbox,
  InputTypeIn,
  Modal,
  Text,
} from "@opal/components";
import { SvgBarChart, SvgSliders, SvgThermometer } from "@opal/icons";
import { ContentAction, InputVertical, Section } from "@opal/layouts";
import { Disabled } from "@opal/core";
import type { IconFunctionComponent } from "@opal/types";
import { isAnthropic } from "@/lib/languageModels/svc";
import type {
  LLMModality,
  ModelConfiguration,
} from "@/lib/languageModels/types";
import { modelDisplayName } from "@/lib/languageModels/utils";
import {
  ALL_REASONING_STOPS,
  PaneSlider,
  REASONING_STOP_LABEL_KEYS,
  maxReasoningStop,
  reasoningStopIndex,
} from "@/sections/model-selector/setting-controls";

const UNSET_REASONING_STOP = ALL_REASONING_STOPS.indexOf("medium");
const UNSET_TEMPERATURE = 0;
const TEMPERATURE_MARK_COUNT = 3;
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

interface SectionHeaderProps {
  icon: IconFunctionComponent;
  title: string;
  caption: string;
}

function SectionHeader({ icon, title, caption }: SectionHeaderProps) {
  return (
    <Section
      alignItems="stretch"
      width="auto"
      height="auto"
      className="mx-2 mb-0.5 mt-2"
    >
      <ContentAction
        sizePreset="main-ui"
        variant="section"
        icon={icon}
        title={title}
        description={caption}
        padding={0}
      />
    </Section>
  );
}

interface PolicySliderProps {
  label: string;
  value: number;
  max: number;
  step: number;
  marks: string[];
  activeMark: number;
  onChange: (value: number) => void;
}

function PolicySlider({
  label,
  value,
  max,
  step,
  marks,
  activeMark,
  onChange,
}: PolicySliderProps) {
  return (
    <Section
      alignItems="stretch"
      width="auto"
      height="auto"
      gap={0}
      className="ms-8 me-2"
    >
      <Section alignItems="start" width="auto" height="auto" className="mx-0.5">
        <Text font="secondary-action" color="text-03" nowrap>
          {label}
        </Text>
      </Section>
      <Section alignItems="stretch" height="auto" padding={0.5}>
        <PaneSlider
          compact
          value={value}
          min={0}
          max={max}
          step={step}
          onValueChange={onChange}
          onValueCommit={onChange}
        />
        <Section flexDirection="row" justifyContent="between" height={0.75}>
          {marks.map((mark, index) => (
            <Text
              key={mark}
              font="figure-small-value"
              color={index === activeMark ? "text-04" : "text-02"}
              nowrap
            >
              {mark}
            </Text>
          ))}
        </Section>
      </Section>
    </Section>
  );
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

export function ModelSettingsPopover({
  model,
  onChange,
  onOpenChange,
  canEditModelId = false,
}: ModelSettingsPopoverProps) {
  const t = useTranslations("admin.languageModels.modals");
  const tModelSelector = useTranslations("chat.modelSelector");
  const [open, setOpen] = useState(false);
  function handleOpenChange(next: boolean) {
    setOpen(next);
    onOpenChange?.(next);
  }

  const supportedStop = maxReasoningStop(model.supported_reasoning_efforts);
  const showReasoning = model.supports_reasoning && supportedStop >= 0;
  const temperatureDisabled = model.supports_reasoning;
  const maxTemperature = isAnthropic(model.vendor ?? "", model.name) ? 1 : 2;

  const maxStop = reasoningStopIndex(model.reasoning_effort_max);
  const rawDefaultStop = reasoningStopIndex(model.reasoning_effort_default);
  const effectiveMaxStop =
    maxStop >= 0 ? Math.min(maxStop, supportedStop) : supportedStop;
  const defaultStop =
    rawDefaultStop >= 0 ? Math.min(rawDefaultStop, effectiveMaxStop) : -1;
  const defaultSliderStop =
    defaultStop >= 0
      ? defaultStop
      : Math.min(UNSET_REASONING_STOP, effectiveMaxStop);

  const reasoningMarks = ALL_REASONING_STOPS.slice(0, supportedStop + 1).map(
    (stop) => tModelSelector(REASONING_STOP_LABEL_KEYS[stop])
  );
  const temperatureMarks = [
    tModelSelector("temperature.deterministic.label"),
    tModelSelector("temperature.balanced.label"),
    tModelSelector("temperature.creative.label"),
  ];
  const temperature = model.temperature_default ?? UNSET_TEMPERATURE;
  const temperatureMark = Math.min(
    Math.floor((temperature / maxTemperature) * TEMPERATURE_MARK_COUNT),
    TEMPERATURE_MARK_COUNT - 1
  );
  const inputModalities = resolvedInputModalities(model);

  function setMax(stop: number) {
    const newMaxStop = Math.min(stop, supportedStop);
    const effort = ALL_REASONING_STOPS[newMaxStop];
    if (!effort) return;
    const patch: ModelSettingsPatch = { reasoning_effort_max: effort };
    if (rawDefaultStop > newMaxStop) {
      patch.reasoning_effort_default = effort;
    }
    onChange(patch);
  }

  function setDefault(stop: number) {
    const effort = ALL_REASONING_STOPS[Math.min(stop, effectiveMaxStop)];
    if (effort) onChange({ reasoning_effort_default: effort });
  }

  function toggleInputType(type: Exclude<LLMModality, "text">, checked: boolean) {
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
              <InputVertical
                title={t("modelSettings.inputTypes.title")}
                subDescription={t("modelSettings.inputTypes.description")}
              >
                <Section alignItems="stretch" height="auto" gap={1.5}>
                  <Disabled
                    disabled
                    tooltip={t("modelSettings.inputTypes.textLocked.tooltip")}
                  >
                    <Section flexDirection="row" alignItems="center" gap={1.5}>
                      <Checkbox
                        checked
                        aria-label={t("modelSettings.types.text.label")}
                      />
                      <Text font="main-ui-body">
                        {t("modelSettings.types.text.label")}
                      </Text>
                    </Section>
                  </Disabled>
                  {INPUT_TYPE_OPTIONS.map((type) => (
                    <Section
                      key={type}
                      flexDirection="row"
                      alignItems="center"
                      gap={1.5}
                    >
                      <Checkbox
                        checked={inputModalities.includes(type)}
                        aria-label={t(`modelSettings.types.${type}.label`)}
                        onCheckedChange={(checked) =>
                          toggleInputType(type, checked)
                        }
                      />
                      <Text font="main-ui-body">
                        {t(`modelSettings.types.${type}.label`)}
                      </Text>
                    </Section>
                  ))}
                </Section>
              </InputVertical>
              <InputVertical
                title={t("modelSettings.outputTypes.title")}
                subDescription={t("modelSettings.outputTypes.description")}
              >
                <Disabled
                  disabled
                  tooltip={t("modelSettings.outputTypes.textLocked.tooltip")}
                >
                  <Section flexDirection="row" alignItems="center" gap={1.5}>
                    <Checkbox
                      checked
                      aria-label={t("modelSettings.types.text.label")}
                    />
                    <Text font="main-ui-body">
                      {t("modelSettings.types.text.label")}
                    </Text>
                  </Section>
                </Disabled>
              </InputVertical>

              {showReasoning && (
                <Section alignItems="stretch" height="auto" gap={0.375}>
                  <SectionHeader
                    icon={SvgBarChart}
                    title={tModelSelector("reasoningLevel.row.title")}
                    caption={tModelSelector("reasoningLevel.row.caption")}
                  />
                  <PolicySlider
                    label={t("modelSettings.reasoningLevel.maxSlider.label")}
                    value={effectiveMaxStop}
                    max={supportedStop}
                    step={1}
                    marks={reasoningMarks}
                    activeMark={effectiveMaxStop}
                    onChange={setMax}
                  />
                  <PolicySlider
                    label={t("modelSettings.reasoningLevel.defaultSlider.label")}
                    value={defaultSliderStop}
                    max={supportedStop}
                    step={1}
                    marks={reasoningMarks}
                    activeMark={defaultSliderStop}
                    onChange={setDefault}
                  />
                </Section>
              )}

              <Disabled
                disabled={temperatureDisabled}
                tooltip={t("modelSettings.temperature.pinned.tooltip")}
                tooltipSide="top"
              >
                <Section alignItems="stretch" height="auto" gap={0.375}>
                  <SectionHeader
                    icon={SvgThermometer}
                    title={tModelSelector("temperature.row.title")}
                    caption={tModelSelector("temperature.row.caption")}
                  />
                  <PolicySlider
                    label={t("modelSettings.temperature.defaultSlider.label")}
                    value={temperatureDisabled ? 1 : temperature}
                    max={maxTemperature}
                    step={0.1}
                    marks={temperatureMarks}
                    activeMark={temperatureMark}
                    onChange={(v) => onChange({ temperature_default: v })}
                  />
                </Section>
              </Disabled>
            </Section>
          </Modal.Body>
        </Modal.Content>
      </Modal>
    </>
  );
}
