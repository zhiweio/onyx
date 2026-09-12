"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { Popover, PopoverMenu, Text } from "@opal/components";
import { SvgChevronDown, SvgFolder } from "@opal/icons";
import { cn } from "@opal/utils";
import { CRAFT_PROJECTS_PATH } from "@/app/craft/v1/constants";
import { useCraftProjects } from "@/lib/craft-projects/hooks";
import { isImplicitUntitledProject } from "@/lib/craft-projects/display";
import { useCraftSessionProjectControls } from "@/app/craft/components/CraftSessionProjectControls";

interface CraftSessionProjectCrumbProps {
  sessionId: string;
  projectId: string | null;
  sessionTitle: string;
}

export default function CraftSessionProjectCrumb({
  sessionId,
  projectId,
  sessionTitle,
}: CraftSessionProjectCrumbProps) {
  const t = useTranslations("craft.sideBar");
  const { data: projects, refresh } = useCraftProjects();
  const [open, setOpen] = useState(false);
  const visibleProjects = useMemo(
    () => projects.filter((project) => !isImplicitUntitledProject(project)),
    [projects]
  );
  const project = visibleProjects.find((item) => item.id === projectId) ?? null;
  const { menuItems, modal } = useCraftSessionProjectControls({
    sessionId,
    projectId,
    sessionTitle,
    projects: visibleProjects,
    onProjectsChanged: refresh,
  });

  const label = project
    ? project.name
    : t("sessionProject.ungrouped.label");
  const href = project
    ? (`${CRAFT_PROJECTS_PATH}/${project.id}` as Route)
    : undefined;

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <div className="flex min-w-0 items-center gap-1">
          {href ? (
            <Link
              href={href}
              className="flex min-w-0 items-center gap-1 px-1.5 py-1 rounded-08 hover:bg-background-tint-01"
            >
              <SvgFolder className="w-4 h-4 stroke-text-03 shrink-0" />
              <Text font="secondary-action" color="text-03" nowrap>
                {label}
              </Text>
            </Link>
          ) : (
            <span className="flex min-w-0 items-center gap-1 px-1.5 py-1">
              <SvgFolder className="w-4 h-4 stroke-text-03 shrink-0" />
              <Text font="secondary-action" color="text-03" nowrap>
                {label}
              </Text>
            </span>
          )}
          <Popover.Trigger asChild>
            <button
              type="button"
              aria-label={t("sessionProject.menu.ariaLabel")}
              className={cn(
                "flex items-center rounded-08 p-1",
                "transition-colors hover:bg-background-tint-01",
                open && "bg-background-tint-01"
              )}
            >
              <SvgChevronDown className="w-3.5 h-3.5 stroke-text-03" />
            </button>
          </Popover.Trigger>
        </div>
        <Popover.Content side="bottom" align="start">
          <PopoverMenu>{menuItems}</PopoverMenu>
        </Popover.Content>
      </Popover>
      {modal}
    </>
  );
}
