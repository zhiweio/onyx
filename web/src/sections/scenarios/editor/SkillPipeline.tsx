"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import {
  Button,
  InputTypeIn,
  Popover,
  Tag,
  Text,
  Tooltip,
} from "@opal/components";
import { Content } from "@opal/layouts";
import { SvgHandle, SvgPlus, SvgTrash } from "@opal/icons";
import { cn } from "@opal/utils";
import type { SkillOption } from "@/sections/scenarios/editor/types";

interface SkillPipelineProps {
  skillKeys: string[];
  skillCatalog: SkillOption[];
  fieldsLocked: boolean;
  onChange: (skillKeys: string[]) => void;
}

interface SortableSkillRowProps {
  skill: SkillOption;
  index: number;
  fieldsLocked: boolean;
  onRemove: () => void;
  onMove: (delta: number) => void;
}

function SortableSkillRow({
  skill,
  index,
  fieldsLocked,
  onRemove,
  onMove,
}: SortableSkillRowProps) {
  const t = useTranslations("craft.scenarioEditor");
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: skill.key, disabled: fieldsLocked });

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      data-testid={`SkillPipeline/row-${skill.key}`}
      className={cn(
        "flex items-center gap-2 rounded-08 border border-border-01 bg-background-neutral-00 px-2 py-1.5",
        isDragging && "z-10 shadow-md"
      )}
    >
      <button
        type="button"
        className="text-text-03"
        aria-label={t("pipeline.drag.ariaLabel")}
        disabled={fieldsLocked}
        {...attributes}
        {...listeners}
        onKeyDown={(event) => {
          listeners?.onKeyDown?.(event);
          if (fieldsLocked) return;
          if (event.key === "ArrowDown") {
            event.preventDefault();
            onMove(1);
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            onMove(-1);
          }
        }}
      >
        <SvgHandle />
      </button>
      <Text font="secondary-body" color="text-03" nowrap>
        {String(index + 1).padStart(2, "0")}
      </Text>
      <Tooltip tooltip={skill.description || skill.name} side="top">
        <div className="min-w-0 flex-1 overflow-hidden">
          <Text font="main-ui-body" nowrap>
            {skill.name}
          </Text>
        </div>
      </Tooltip>
      <Button
        size="sm"
        prominence="tertiary"
        icon={SvgTrash}
        disabled={fieldsLocked}
        aria-label={t("pipeline.remove.ariaLabel", { name: skill.name })}
        onClick={onRemove}
      />
    </div>
  );
}

export default function SkillPipeline({
  skillKeys,
  skillCatalog,
  fieldsLocked,
  onChange,
}: SkillPipelineProps) {
  const t = useTranslations("craft.scenarioEditor");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const skillByKey = useMemo(() => {
    const map = new Map<string, SkillOption>();
    for (const skill of skillCatalog) {
      map.set(skill.key, skill);
    }
    return map;
  }, [skillCatalog]);

  const traySkills = skillKeys.map((key) => {
    return skillByKey.get(key) ?? { key, name: key, description: "" };
  });

  const visibleCatalog = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return skillCatalog.filter((skill) => {
      if (!needle) return true;
      return (
        skill.name.toLowerCase().includes(needle) ||
        skill.description.toLowerCase().includes(needle) ||
        skill.key.toLowerCase().includes(needle)
      );
    });
  }, [query, skillCatalog]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = skillKeys.indexOf(String(active.id));
    const newIndex = skillKeys.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    onChange(arrayMove(skillKeys, oldIndex, newIndex));
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Content
          title={t("pipeline.title")}
          description={t("pipeline.count.label", { count: traySkills.length })}
          sizePreset="main-content"
          variant="section"
        />
        <Popover
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (next) setQuery("");
          }}
        >
          <Popover.Trigger asChild>
            <Button
              size="sm"
              prominence="secondary"
              icon={SvgPlus}
              disabled={fieldsLocked}
              data-testid="SkillPipeline/add"
            >
              {t("pipeline.add.label")}
            </Button>
          </Popover.Trigger>
          <Popover.Content width="2xl" align="end" side="bottom">
            <div className="flex w-80 flex-col gap-2 p-2">
              <InputTypeIn
                searchIcon
                value={query}
                placeholder={t("pipeline.add.search.placeholder")}
                onChange={(event) => setQuery(event.target.value)}
              />
              <div className="max-h-72 overflow-y-auto">
                {visibleCatalog.length === 0 ? (
                  <div className="px-2 py-3">
                    <Text color="text-03">{t("pipeline.add.empty.text")}</Text>
                  </div>
                ) : (
                  visibleCatalog.map((skill) => {
                    const added = skillKeys.includes(skill.key);
                    return (
                      <div
                        key={skill.key}
                        data-testid={`SkillPipeline/catalog-${skill.key}`}
                        className="flex items-center gap-2 rounded-08 px-2 py-1.5 hover:bg-background-tint-02"
                      >
                        <div className="min-w-0 flex-1 overflow-hidden">
                          <Text font="main-ui-body" nowrap>
                            {skill.name}
                          </Text>
                          <Text font="secondary-body" color="text-03" maxLines={1}>
                            {skill.description}
                          </Text>
                        </div>
                        {added ? (
                          <Tag size="sm" color="gray" title={t("pipeline.added.label")} />
                        ) : (
                          <Button
                            size="sm"
                            prominence="secondary"
                            disabled={fieldsLocked}
                            onClick={() => onChange([...skillKeys, skill.key])}
                          >
                            {t("pipeline.add.label")}
                          </Button>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </Popover.Content>
        </Popover>
      </div>

      {traySkills.length === 0 ? (
        <div className="flex min-h-40 flex-1 items-center justify-center rounded-12 border border-dashed border-border-02 px-4 text-center">
          <Text color="text-03">{t("pipeline.empty.text")}</Text>
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToVerticalAxis]}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={skillKeys} strategy={verticalListSortingStrategy}>
            <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
              {traySkills.map((skill, index) => (
                <SortableSkillRow
                  key={skill.key}
                  skill={skill}
                  index={index}
                  fieldsLocked={fieldsLocked}
                  onRemove={() =>
                    onChange(skillKeys.filter((key) => key !== skill.key))
                  }
                  onMove={(delta) => {
                    const nextIndex = index + delta;
                    if (nextIndex < 0 || nextIndex >= skillKeys.length) return;
                    onChange(arrayMove(skillKeys, index, nextIndex));
                  }}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}
