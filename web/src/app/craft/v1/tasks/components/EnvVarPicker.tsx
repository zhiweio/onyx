"use client";

import { useTranslations } from "next-intl";
import { Card, Checkbox, Text } from "@opal/components";
import { SvgKey, SvgTerminal } from "@opal/icons";
import type { IconFunctionComponent } from "@opal/types";
import { cn } from "@opal/utils";
import { useEnvVars } from "@/hooks/useEnvVars";
import type { EnvVarItem } from "@/app/craft/v1/env-vars/interfaces";

interface EnvVarPickerProps {
  /** The task's project; ``null`` means only personal vars are grantable. */
  projectId: string | null;
  selectedEnvVarIds: string[];
  onChange: (ids: string[]) => void;
}

function toggledId(selectedIds: string[], id: string): string[] {
  return selectedIds.includes(id)
    ? selectedIds.filter((selectedId) => selectedId !== id)
    : [...selectedIds, id];
}

/**
 * Explicit per-task grant picker (GitHub Actions semantics): a var is only
 * substituted into runs when its checkbox is on. Personal rows are always
 * listed; project rows appear when the task belongs to a project.
 */
export default function EnvVarPicker({
  projectId,
  selectedEnvVarIds,
  onChange,
}: EnvVarPickerProps) {
  const t = useTranslations("craft.tasks.envVarPicker");
  const { data: envVars, isLoading, error } = useEnvVars(projectId);

  const personalOptions = envVars.filter((item) => item.scope === "USER");
  const projectOptions = envVars.filter((item) => item.scope === "PROJECT");
  const knownIds = new Set(envVars.map((item) => item.id));
  // Selected ids whose row is no longer grantable (deleted, or project
  // changed) — kept visible as unavailable so the state is not a mystery.
  const staleOptions: EnvVarItem[] = selectedEnvVarIds
    .filter((id) => !knownIds.has(id))
    .map((id) => ({
      id,
      name: t("staleFallbackName", { id }),
      is_secret: false,
      scope: "USER",
      project_id: null,
      project_name: null,
      value: null,
      manageable: false,
      created_at: "",
      updated_at: "",
    }));
  const hasOptions =
    personalOptions.length > 0 ||
    projectOptions.length > 0 ||
    staleOptions.length > 0;

  if (isLoading && !hasOptions) {
    return (
      <Card background="none" border="dashed" rounding={4}>
        <Text font="secondary-body" color="text-03">
          {t("loading.label")}
        </Text>
      </Card>
    );
  }

  if (error && !hasOptions) {
    return (
      <Card background="none" border="dashed" rounding={4}>
        <Text font="secondary-body" color="text-03">
          {t("errors.loadFailed")}
        </Text>
      </Card>
    );
  }

  if (!hasOptions) {
    return (
      <Card background="none" border="dashed" rounding={4}>
        <Text font="secondary-body" color="text-03">
          {projectId ? t("empty.label") : t("empty.noProjectLabel")}
        </Text>
      </Card>
    );
  }

  return (
    <div className="flex w-full flex-col gap-4" data-testid="env-var-picker">
      {error && (
        <Card background="none" border="dashed" rounding={4}>
          <Text font="secondary-body" color="text-03">
            {t("errors.partialLoadFailed")}
          </Text>
        </Card>
      )}
      {personalOptions.length + staleOptions.length > 0 && (
        <EnvVarGroup
          title={t("personalGroupTitle")}
          options={[...personalOptions, ...staleOptions]}
          selectedIds={selectedEnvVarIds}
          onToggle={(id) => onChange(toggledId(selectedEnvVarIds, id))}
          unavailableIds={new Set(staleOptions.map((option) => option.id))}
        />
      )}
      {projectOptions.length > 0 && (
        <EnvVarGroup
          title={t("projectGroupTitle", {
            name: projectOptions[0]?.project_name ?? "",
          })}
          options={projectOptions}
          selectedIds={selectedEnvVarIds}
          onToggle={(id) => onChange(toggledId(selectedEnvVarIds, id))}
          unavailableIds={new Set<string>()}
        />
      )}
      <Text font="secondary-body" color="text-03">
        {t("usageHint")}
      </Text>
    </div>
  );
}

interface EnvVarGroupProps {
  title: string;
  options: EnvVarItem[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  unavailableIds: Set<string>;
}

function EnvVarGroup({
  title,
  options,
  selectedIds,
  onToggle,
  unavailableIds,
}: EnvVarGroupProps) {
  const selected = new Set(selectedIds);
  return (
    <section className="flex flex-col gap-2" aria-label={title}>
      <Text as="h3" font="main-ui-action" color="text-03">
        {title}
      </Text>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {options.map((option) => (
          <EnvVarRow
            key={option.id}
            option={option}
            checked={selected.has(option.id)}
            unavailable={unavailableIds.has(option.id)}
            onToggle={() => onToggle(option.id)}
          />
        ))}
      </div>
    </section>
  );
}

interface EnvVarRowProps {
  option: EnvVarItem;
  checked: boolean;
  unavailable: boolean;
  onToggle: () => void;
}

function EnvVarRow({ option, checked, unavailable, onToggle }: EnvVarRowProps) {
  const t = useTranslations("craft.tasks.envVarPicker");
  const Icon: IconFunctionComponent = option.is_secret ? SvgKey : SvgTerminal;
  const checkboxId = `env-var-${option.id}-checkbox`;
  const statusId = `env-var-${option.id}-status`;
  const status = unavailable
    ? t("status.unavailable")
    : option.is_secret
      ? t("status.secret")
      : option.value;
  return (
    <div
      className={cn(
        "rounded-12 focus-within:outline-none focus-within:ring-2 focus-within:ring-action-selection-04",
        checked && "ring-2 ring-action-selection-04"
      )}
      data-testid={`env-var-option-${option.id}`}
    >
      <Card background="light" border="solid" rounding={4}>
        <label
          className="flex w-full cursor-pointer items-center gap-3"
          htmlFor={checkboxId}
        >
          <Icon className="w-8 h-8" />
          <div className="flex-1 flex flex-col gap-1 min-w-0">
            <Text font="main-ui-action" className="break-all">
              {option.name}
            </Text>
            <Text
              id={statusId}
              font="secondary-body"
              color="text-03"
              className="break-all"
            >
              {status}
            </Text>
          </div>
          <Checkbox
            id={checkboxId}
            aria-label={option.name}
            aria-describedby={statusId}
            checked={checked}
            onCheckedChange={onToggle}
          />
        </label>
      </Card>
    </div>
  );
}
