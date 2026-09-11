"use client";

import { useCallback, type MouseEvent } from "react";
import { useTranslations } from "next-intl";
import { Button, Tag } from "@opal/components";
import { Content } from "@opal/layouts";
import {
  SvgCopy,
  SvgEdit,
  SvgPlayCircle,
  SvgShare,
  SvgTrash,
} from "@opal/icons";
import { CardItemLayout } from "@/layouts/general-layouts";
import { Interactive } from "@opal/core";
import { Card } from "@/refresh-components/cards";
import { cn } from "@opal/utils";
import {
  canEditScenario,
  isWorkspaceScenario,
  isBuiltinScenarioDomain,
  isUncategorizedDomain,
  scenarioDomain,
  scenarioDomainMessageKey,
  scenarioDomainTagColor,
  UNCATEGORIZED_SCENARIO_DOMAIN,
  type Scenario,
} from "@/lib/scenarios/types";
import type { CatalogViewMode } from "@/lib/system-catalog/types";

export interface ScenarioCardProps {
  scenario: Scenario;
  skillNames: string[];
  onClick?: (scenario: Scenario) => void;
  onEdit?: (scenario: Scenario) => void;
  onCustomize?: (scenario: Scenario) => void;
  onShare?: (scenario: Scenario) => void;
  onDelete?: (scenario: Scenario) => void;
  onStart?: (scenario: Scenario) => void;
  startPending?: boolean;
  customizePending?: boolean;
  layout?: CatalogViewMode;
}

function stopAndCall(
  event: MouseEvent<HTMLElement>,
  handler: ((scenario: Scenario) => void) | undefined,
  scenario: Scenario
) {
  event.stopPropagation();
  handler?.(scenario);
}

export default function ScenarioCard({
  scenario,
  skillNames,
  onClick,
  onEdit,
  onCustomize,
  onShare,
  onDelete,
  onStart,
  startPending = false,
  customizePending = false,
  layout = "cards",
}: ScenarioCardProps) {
  const t = useTranslations("craft.scenarios");
  const domain = scenarioDomain(scenario);
  const visibleSkills = skillNames.slice(0, 4);
  const extraCount = Math.max(skillNames.length - visibleSkills.length, 0);
  const canEdit = canEditScenario(scenario);
  const workspacePack = isWorkspaceScenario(scenario);

  const handleClick = useCallback(() => {
    onClick?.(scenario);
  }, [onClick, scenario]);

  const leadAction = canEdit ? (
    <Button
      prominence="secondary"
      size="sm"
      icon={SvgEdit}
      tooltip={t("card.edit.tooltip")}
      aria-label={t("card.edit.tooltip")}
      onClick={(event) => stopAndCall(event, onEdit, scenario)}
    />
  ) : (
    <Button
      prominence="secondary"
      size="sm"
      icon={SvgCopy}
      tooltip={t("card.customize.tooltip")}
      aria-label={t("card.customize.tooltip")}
      disabled={customizePending}
      onClick={(event) => stopAndCall(event, onCustomize, scenario)}
    />
  );

  if (layout === "list") {
    return (
      <Interactive.Simple onClick={handleClick} group="group/ScenarioCard">
        <Card variant="primary" padding={1} gap={0}>
          <div className="flex w-full flex-row items-center justify-between gap-2">
            <div className="min-w-0 flex-1">
              <Content
                icon={SvgShare}
                title={scenario.name}
                description={scenario.description}
                sizePreset="main-ui"
                variant="section"
              />
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {leadAction}
              <Button
                prominence="primary"
                size="sm"
                icon={SvgPlayCircle}
                disabled={startPending}
                onClick={(event) => stopAndCall(event, onStart, scenario)}
              >
                {t("card.startRun.label")}
              </Button>
            </div>
          </div>
        </Card>
      </Interactive.Simple>
    );
  }

  return (
    <Interactive.Simple onClick={handleClick} group="group/ScenarioCard">
      <Card variant="primary" padding={0} gap={0} height="full">
        <div className="flex self-stretch min-h-24">
          <CardItemLayout
            icon={SvgShare}
            title={scenario.name}
            description={scenario.description}
            rightChildren={leadAction}
          />
        </div>
        <div className="px-2 pb-2 flex flex-wrap gap-1">
          {visibleSkills.map((name) => (
            <Tag key={name} title={name} color="gray" />
          ))}
          {extraCount > 0 && (
            <Tag
              title={t("card.moreSkills.label", { count: extraCount })}
              color="gray"
            />
          )}
        </div>
        <div className="bg-background-tint-01 p-1.5 flex flex-col gap-1.5 w-full">
          <div className="px-1 flex flex-wrap gap-1">
            <Tag
              title={
                workspacePack
                  ? t("card.origin.workspace.label")
                  : t("card.origin.personal.label")
              }
              color={workspacePack ? "blue" : "purple"}
            />
            <Tag
              title={t(
                scenario.public_permission
                  ? "card.visibility.public.label"
                  : "card.visibility.private.label"
              )}
              color="gray"
            />
            <Tag
              title={
                isBuiltinScenarioDomain(domain)
                  ? t(scenarioDomainMessageKey(domain))
                  : isUncategorizedDomain(domain)
                    ? t(scenarioDomainMessageKey(UNCATEGORIZED_SCENARIO_DOMAIN))
                    : domain
              }
              color={scenarioDomainTagColor(domain)}
            />
          </div>
          <div className="flex flex-row items-center justify-between w-full">
            <div className="py-1 px-1 min-w-0 flex-1">
              <Content
                icon={SvgShare}
                title={t("card.skillCount.label", {
                  count: skillNames.length,
                })}
                sizePreset="secondary"
                variant="body"
                color="muted"
              />
            </div>
            <div className={cn("flex items-center gap-1")}>
              {canEdit && (
                <>
                  <Button
                    prominence="tertiary"
                    size="sm"
                    icon={SvgShare}
                    tooltip={t("card.share.tooltip")}
                    aria-label={t("card.share.tooltip")}
                    onClick={(event) => stopAndCall(event, onShare, scenario)}
                  />
                  <Button
                    prominence="tertiary"
                    size="sm"
                    icon={SvgTrash}
                    tooltip={t("card.delete.tooltip")}
                    aria-label={t("delete.title", { name: scenario.name })}
                    onClick={(event) => stopAndCall(event, onDelete, scenario)}
                  />
                </>
              )}
              <Button
                prominence="primary"
                size="sm"
                icon={SvgPlayCircle}
                disabled={startPending}
                onClick={(event) => stopAndCall(event, onStart, scenario)}
              >
                {t("card.startRun.label")}
              </Button>
            </div>
          </div>
        </div>
      </Card>
    </Interactive.Simple>
  );
}
