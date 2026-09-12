"use client";

import * as React from "react";
import {
  closestCenter,
  DndContext,
  DragOverlay,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  horizontalListSortingStrategy,
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ScrollArea as ScrollAreaPrimitive } from "radix-ui";

import { cn } from "@/sections/extend/lib/utils";
import { Button } from "@/sections/extend/ui/button";
import {
  ScrollArea as InlineScrollArea,
  ScrollBar,
} from "@/sections/extend/ui/scroll-area";
import { FileThumbnail } from "@/sections/extend/file-thumbnail";
import { IconPlaceholder } from "@/sections/icon-placeholder";

export type DocumentSplitPageId = `page-${number}`;
export type DocumentSplit = {
  id: string;
  title: string;
  pages: DocumentSplitPageId[];
};
type PageId = DocumentSplitPageId;
type SplitGroup = DocumentSplit;
const THUMBNAIL_WIDTH = 72;
const THUMBNAIL_HEIGHT = 92;
const DRAG_OVERLAY_DROP_ANIMATION = null;
const THUMBNAIL_SURFACE_CLASS_NAME =
  "relative overflow-hidden rounded-lg border border-oklch(0.922 0 0) bg-oklch(1 0 0) shadow-xs dark:border-oklch(1 0 0 / 10%) dark:bg-oklch(0.145 0 0)";
const THUMBNAIL_BUTTON_CLASS_NAME = cn(
  THUMBNAIL_SURFACE_CLASS_NAME,
  "cursor-grab text-left transition-[border-color,box-shadow,opacity] outline-none hover:border-oklch(0.708 0 0)/40 hover:ring-2 hover:ring-oklch(0.708 0 0) focus-visible:border-oklch(0.708 0 0)/40 focus-visible:ring-2 focus-visible:ring-oklch(0.708 0 0) active:cursor-grabbing dark:hover:border-oklch(0.556 0 0)/40 dark:hover:ring-oklch(0.556 0 0) dark:focus-visible:border-oklch(0.556 0 0)/40 dark:focus-visible:ring-oklch(0.556 0 0)"
);
const splitterCollisionDetection: CollisionDetection = (args) => {
  const dragType = args.active.data.current?.type;
  if (dragType === "page") {
    return closestCenter({
      ...args,
      droppableContainers: args.droppableContainers.filter(
        (container) =>
          container.data.current?.type === "page" ||
          (container.data.current?.type === "page-dropzone" &&
            container.data.current?.isEmpty)
      ),
    });
  }
  if (dragType === "split") {
    return closestCenter({
      ...args,
      droppableContainers: args.droppableContainers.filter(
        (container) => container.data.current?.type === "split"
      ),
    });
  }
  return closestCenter(args);
};
export const INITIAL_SPLITS: DocumentSplit[] = [
  {
    id: "split-1",
    title: "Abstract and intro",
    pages: ["page-1", "page-2", "page-3"],
  },
  {
    id: "split-2",
    title: "Model architecture",
    pages: ["page-4", "page-5", "page-6", "page-7"],
  },
  {
    id: "split-3",
    title: "Training and results",
    pages: ["page-8", "page-9", "page-10"],
  },
];
export function createInitialSplits(pageCount: number) {
  if (pageCount <= 0) return INITIAL_SPLITS;
  const pages = Array.from(
    { length: pageCount },
    (_, index) => `page-${index + 1}` as PageId
  );
  const chunkSize = Math.max(1, Math.ceil(pageCount / 3));
  return Array.from(
    { length: Math.ceil(pageCount / chunkSize) },
    (_, index) => {
      const startIndex = index * chunkSize;
      const groupPages = pages.slice(startIndex, startIndex + chunkSize);
      const firstPage = getPageNumber(groupPages[0]);
      const lastPage = getPageNumber(groupPages[groupPages.length - 1]);
      return {
        id: `split-${index + 1}`,
        title:
          firstPage === lastPage
            ? `Page ${firstPage}`
            : `Pages ${firstPage}-${lastPage}`,
        pages: groupPages,
      };
    }
  );
}
function getPageNumber(pageId: PageId) {
  return Number(pageId.replace("page-", ""));
}
function getSplitSortableId(groupId: string) {
  return `split-sortable-${groupId}`;
}
function findGroupId(groups: SplitGroup[], id: string) {
  if (groups.some((group) => group.id === id)) return id;
  return groups.find((group) => group.pages.includes(id as PageId))?.id ?? null;
}
function getGroupPages(groups: SplitGroup[], groupId: string | null) {
  return groups.find((group) => group.id === groupId)?.pages ?? [];
}
function movePageToGroup({
  draggedPageId,
  groups,
  insertIndex,
  targetGroupId,
}: {
  draggedPageId: PageId;
  groups: SplitGroup[];
  insertIndex: number;
  targetGroupId: string;
}) {
  return groups.map((group) => {
    const pagesWithoutDragged = group.pages.filter(
      (pageId) => pageId !== draggedPageId
    );
    if (group.id !== targetGroupId) {
      return { ...group, pages: pagesWithoutDragged };
    }
    const nextPages = [...pagesWithoutDragged];
    nextPages.splice(insertIndex, 0, draggedPageId);
    return { ...group, pages: nextPages };
  });
}
function areSplitGroupsEqual(left: SplitGroup[], right: SplitGroup[]) {
  if (left === right) return true;
  if (left.length !== right.length) return false;
  return left.every((leftGroup, groupIndex) => {
    const rightGroup = right[groupIndex];
    if (!rightGroup) return false;
    return (
      leftGroup.id === rightGroup.id &&
      leftGroup.title === rightGroup.title &&
      leftGroup.pages.length === rightGroup.pages.length &&
      leftGroup.pages.every(
        (pageId, pageIndex) => pageId === rightGroup.pages[pageIndex]
      )
    );
  });
}
function reorderPageInGroup({
  draggedPageId,
  groups,
  overPageId,
}: {
  draggedPageId: PageId;
  groups: SplitGroup[];
  overPageId: PageId;
}) {
  const groupId = findGroupId(groups, draggedPageId);
  const pages = getGroupPages(groups, groupId);
  const draggedIndex = pages.indexOf(draggedPageId);
  const overIndex = pages.indexOf(overPageId);
  if (!groupId || draggedIndex === -1 || overIndex === -1) return groups;
  return groups.map((group) =>
    group.id === groupId
      ? {
          ...group,
          pages: arrayMove(group.pages, draggedIndex, overIndex),
        }
      : group
  );
}
function createPageRangeLabel(pageIds: PageId[]) {
  if (pageIds.length === 0) return "No pages";
  return `Pages ${pageIds.map(getPageNumber).join(",")}`;
}
function SplitGroupDropzone({
  children,
  group,
}: {
  children: React.ReactNode;
  group: SplitGroup;
}) {
  const { isOver, setNodeRef } = useDroppable({
    id: group.id,
    data: { type: "page-dropzone", isEmpty: group.pages.length === 0 },
  });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "min-h-[116px] rounded-lg p-2 transition-[background-color,box-shadow]",
        isOver &&
          "bg-oklch(0.97 0 0)/30 shadow-[inset_0_0_0_1px_var(--border)] dark:bg-oklch(0.269 0 0)/30"
      )}
    >
      {children}
    </div>
  );
}
function PageThumbnail({
  imageUrl,
  onSelect,
  pageId,
}: {
  imageUrl?: string;
  onSelect: (pageNumber: number) => void;
  pageId: PageId;
}) {
  const pageNumber = getPageNumber(pageId);
  const {
    attributes,
    isDragging,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({
    id: pageId,
    data: { type: "page" },
  });
  return (
    <button
      ref={setNodeRef}
      type="button"
      className={cn(
        THUMBNAIL_BUTTON_CLASS_NAME,
        "shrink-0",
        isDragging && "opacity-0"
      )}
      style={{
        width: THUMBNAIL_WIDTH,
        height: THUMBNAIL_HEIGHT,
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      onClick={() => onSelect(pageNumber)}
      {...attributes}
      {...listeners}
    >
      <FileThumbnail
        file={{
          name: `page-${pageNumber}.pdf`,
          type: "application/pdf",
        }}
        previewImageUrl={imageUrl}
        isLoading={!imageUrl}
        previewClassName="h-full aspect-auto"
        className="size-full rounded-[inherit] border-0 bg-transparent"
      />
      <span className="absolute right-1 bottom-1 rounded bg-oklch(1 0 0)/95 px-1.5 py-0.5 text-[10px] font-semibold text-oklch(0.145 0 0) shadow-xs ring-1 ring-oklch(0.922 0 0)/80 dark:bg-oklch(0.145 0 0)/95 dark:text-oklch(0.985 0 0) dark:ring-oklch(1 0 0 / 10%)/80">
        {pageNumber}
      </span>
    </button>
  );
}
function SplitGroupCard({
  canRemove,
  group,
  dragHandleProps,
  thumbnailImages,
  onRemove,
  onSelectPage,
}: {
  canRemove: boolean;
  group: SplitGroup;
  dragHandleProps?: React.ComponentPropsWithoutRef<"button">;
  thumbnailImages: Record<PageId, string>;
  onRemove: () => void;
  onSelectPage: (pageNumber: number) => void;
}) {
  return (
    <section className="w-full rounded-lg border border-oklch(0.922 0 0) bg-oklch(1 0 0) dark:border-oklch(1 0 0 / 10%) dark:bg-oklch(0.145 0 0)">
      <div className="flex items-center justify-between gap-3 border-b p-3">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            aria-label={`Reorder ${group.title}`}
            className="inline-flex size-7 shrink-0 cursor-grab items-center justify-center rounded-md text-oklch(0.556 0 0) hover:bg-oklch(0.97 0 0) active:cursor-grabbing dark:text-oklch(0.708 0 0) dark:hover:bg-oklch(0.269 0 0)"
            {...dragHandleProps}
          >
            <IconPlaceholder
              lucide="GripVertical"
              tabler="IconGripVertical"
              hugeicons="DragDropVerticalIcon"
              phosphor="DotsSixVerticalIcon"
              remixicon="RiDraggable"
              className="size-4"
            />
          </button>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{group.title}</div>
            <div className="mt-1 text-xs text-oklch(0.556 0 0) dark:text-oklch(0.708 0 0)">
              {createPageRangeLabel(group.pages)}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <div className="rounded-full bg-oklch(0.97 0 0) px-2 py-0.5 text-xs text-oklch(0.556 0 0) dark:bg-oklch(0.269 0 0) dark:text-oklch(0.708 0 0)">
            {group.pages.length}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove ${group.title}`}
            disabled={!canRemove}
            onClick={onRemove}
          >
            <IconPlaceholder
              lucide="Trash2Icon"
              tabler="IconTrash"
              hugeicons="Delete02Icon"
              phosphor="TrashIcon"
              remixicon="RiDeleteBinLine"
              className="size-4"
            />
          </Button>
        </div>
      </div>
      <SplitGroupDropzone group={group}>
        {group.pages.length ? (
          <SortableContext
            items={group.pages}
            strategy={horizontalListSortingStrategy}
          >
            <InlineScrollArea2
              className="h-[110px] w-full overflow-hidden"
              orientation="horizontal"
              scrollbarGutter
              scrollbarOverflowOnly
              viewportClassName="overflow-y-hidden"
            >
              <div className="flex w-max gap-2 overflow-y-hidden py-1 pr-6">
                {group.pages.map((pageId) => (
                  <PageThumbnail
                    key={pageId}
                    pageId={pageId}
                    imageUrl={thumbnailImages[pageId]}
                    onSelect={onSelectPage}
                  />
                ))}
              </div>
            </InlineScrollArea2>
          </SortableContext>
        ) : (
          <div className="grid h-[104px] place-items-center rounded-lg bg-oklch(0.97 0 0)/35 text-xs text-oklch(0.556 0 0) dark:bg-oklch(0.269 0 0)/35 dark:text-oklch(0.708 0 0)">
            Drop pages here
          </div>
        )}
      </SplitGroupDropzone>
    </section>
  );
}
function SortableSplitGroupCard({
  canRemove,
  group,
  thumbnailImages,
  onRemove,
  onSelectPage,
}: {
  canRemove: boolean;
  group: SplitGroup;
  thumbnailImages: Record<PageId, string>;
  onRemove: () => void;
  onSelectPage: (pageNumber: number) => void;
}) {
  const {
    attributes,
    isDragging,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({
    id: getSplitSortableId(group.id),
    data: { type: "split", groupId: group.id },
  });
  return (
    <div
      ref={setNodeRef}
      className={cn("w-full", isDragging && "opacity-0")}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
    >
      <SplitGroupCard
        canRemove={canRemove}
        group={group}
        thumbnailImages={thumbnailImages}
        dragHandleProps={{ ...attributes, ...listeners }}
        onRemove={onRemove}
        onSelectPage={onSelectPage}
      />
    </div>
  );
}
function SplitGroupDragOverlay({
  group,
  thumbnailImages,
  width,
  onSelectPage,
}: {
  group: SplitGroup;
  thumbnailImages: Record<PageId, string>;
  width?: number;
  onSelectPage: (pageNumber: number) => void;
}) {
  return (
    <div className="relative z-40 max-w-[calc(100vw-2rem)]" style={{ width }}>
      <SplitGroupCard
        canRemove={false}
        group={group}
        thumbnailImages={thumbnailImages}
        onRemove={() => {}}
        onSelectPage={onSelectPage}
      />
    </div>
  );
}
export function DocumentSplits({
  className,
  splits,
  thumbnailImages = {},
  withFrameDivider = true,
  onSelectPage,
  onSplitsChange,
}: {
  className?: string;
  splits: SplitGroup[];
  thumbnailImages?: Record<PageId, string>;
  withFrameDivider?: boolean;
  onSelectPage: (pageNumber: number) => void;
  onSplitsChange: (splits: SplitGroup[]) => void;
}) {
  const [draggedPageId, setDraggedPageId] = React.useState<PageId | null>(null);
  const [activeSplitGroupId, setActiveSplitGroupId] = React.useState<
    string | null
  >(null);
  const [activeSplitGroupWidth, setActiveSplitGroupWidth] = React.useState<
    number | undefined
  >();
  const dragStartGroupIdRef = React.useRef<string | null>(null);
  const dragStartSplitsRef = React.useRef<SplitGroup[] | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );
  const handleDragStart = React.useCallback(
    (event: DragStartEvent) => {
      const dragType = event.active.data.current?.type;
      if (dragType === "split") {
        dragStartGroupIdRef.current = null;
        dragStartSplitsRef.current = null;
        setDraggedPageId(null);
        setActiveSplitGroupId(
          (event.active.data.current?.groupId as string | undefined) ?? null
        );
        setActiveSplitGroupWidth(event.active.rect.current.initial?.width);
        return;
      }
      if (dragType !== "page") {
        dragStartGroupIdRef.current = null;
        dragStartSplitsRef.current = null;
        setDraggedPageId(null);
        setActiveSplitGroupId(null);
        setActiveSplitGroupWidth(undefined);
        return;
      }
      const pageId = String(event.active.id) as PageId;
      dragStartGroupIdRef.current = findGroupId(splits, pageId);
      dragStartSplitsRef.current = splits;
      setDraggedPageId(pageId);
      setActiveSplitGroupId(null);
      setActiveSplitGroupWidth(undefined);
    },
    [splits]
  );
  const handleDragOver = React.useCallback(
    (event: DragOverEvent) => {
      if (event.active.data.current?.type !== "page" || !event.over) return;
      const pageId = String(event.active.id) as PageId;
      const overId = String(event.over.id);
      const sourceGroupId = findGroupId(splits, pageId);
      const targetGroupId = findGroupId(splits, overId);
      if (!sourceGroupId || !targetGroupId || sourceGroupId === targetGroupId) {
        return;
      }
      const targetPages = getGroupPages(splits, targetGroupId);
      const overIndex = targetPages.indexOf(overId as PageId);
      const insertIndex = overIndex === -1 ? targetPages.length : overIndex;
      const nextSplits = movePageToGroup({
        draggedPageId: pageId,
        groups: splits,
        insertIndex,
        targetGroupId,
      });
      if (!areSplitGroupsEqual(splits, nextSplits)) {
        onSplitsChange(nextSplits);
      }
    },
    [onSplitsChange, splits]
  );
  const handleDragEnd = React.useCallback(
    (event: DragEndEvent) => {
      if (event.active.data.current?.type === "split" && event.over) {
        const activeGroupId = event.active.data.current.groupId;
        const overGroupId = event.over.data.current?.groupId;
        const draggedIndex = splits.findIndex(
          (group) => group.id === activeGroupId
        );
        const overIndex = splits.findIndex((group) => group.id === overGroupId);
        if (draggedIndex !== -1 && overIndex !== -1) {
          const nextSplits = arrayMove(splits, draggedIndex, overIndex);
          if (!areSplitGroupsEqual(splits, nextSplits)) {
            onSplitsChange(nextSplits);
          }
        }
        dragStartGroupIdRef.current = null;
        dragStartSplitsRef.current = null;
        setDraggedPageId(null);
        setActiveSplitGroupId(null);
        setActiveSplitGroupWidth(undefined);
        return;
      }
      if (event.active.data.current?.type !== "page" || !event.over) {
        dragStartGroupIdRef.current = null;
        dragStartSplitsRef.current = null;
        setDraggedPageId(null);
        setActiveSplitGroupId(null);
        setActiveSplitGroupWidth(undefined);
        return;
      }
      const pageId = String(event.active.id) as PageId;
      const overId = String(event.over.id) as PageId;
      const overGroupId = findGroupId(splits, overId);
      if (dragStartGroupIdRef.current === overGroupId) {
        const nextSplits = reorderPageInGroup({
          draggedPageId: pageId,
          groups: splits,
          overPageId: overId,
        });
        if (!areSplitGroupsEqual(splits, nextSplits)) {
          onSplitsChange(nextSplits);
        }
      }
      dragStartGroupIdRef.current = null;
      dragStartSplitsRef.current = null;
      setDraggedPageId(null);
      setActiveSplitGroupId(null);
      setActiveSplitGroupWidth(undefined);
    },
    [onSplitsChange, splits]
  );
  const handleDragCancel = React.useCallback(() => {
    if (dragStartSplitsRef.current) {
      onSplitsChange(dragStartSplitsRef.current);
    }
    dragStartSplitsRef.current = null;
    dragStartGroupIdRef.current = null;
    setDraggedPageId(null);
    setActiveSplitGroupId(null);
    setActiveSplitGroupWidth(undefined);
  }, [onSplitsChange]);
  const activeSplitGroup = activeSplitGroupId
    ? splits.find((group) => group.id === activeSplitGroupId)
    : null;
  return (
    <aside
      className={cn(
        "flex h-full min-h-0 flex-col bg-oklch(0.97 0 0)/20 dark:bg-oklch(0.269 0 0)/20",
        withFrameDivider && "border-t md:border-t-0 md:border-l",
        className
      )}
    >
      <div className="flex min-h-12 items-center justify-end gap-3 border-b bg-oklch(1 0 0) px-3 dark:bg-oklch(0.145 0 0)">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            onSplitsChange([
              ...splits,
              {
                id: `split-${Date.now()}`,
                title: `Split ${splits.length + 1}`,
                pages: [],
              },
            ])
          }
        >
          <IconPlaceholder
            lucide="Plus"
            tabler="IconPlus"
            hugeicons="Add01Icon"
            phosphor="PlusIcon"
            remixicon="RiAddLine"
            className="size-4"
          />
          Add split
        </Button>
      </div>
      <DndContext
        id="document-splits-dnd"
        sensors={sensors}
        collisionDetection={splitterCollisionDetection}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        <InlineScrollArea2 className="min-h-0 flex-1" scrollFade>
          <SortableContext
            items={splits.map((group) => getSplitSortableId(group.id))}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-3 p-3">
              {splits.map((group) => (
                <SortableSplitGroupCard
                  key={group.id}
                  canRemove={splits.length > 1}
                  group={group}
                  thumbnailImages={thumbnailImages}
                  onRemove={() => {
                    if (splits.length <= 1) return;
                    onSplitsChange(
                      splits.filter((split) => split.id !== group.id)
                    );
                  }}
                  onSelectPage={onSelectPage}
                />
              ))}
            </div>
          </SortableContext>
        </InlineScrollArea2>
        <DragOverlay dropAnimation={DRAG_OVERLAY_DROP_ANIMATION} zIndex={40}>
          {draggedPageId ? (
            <div
              className={cn(
                THUMBNAIL_SURFACE_CLASS_NAME,
                "shadow-lg shadow-black/10"
              )}
              style={{ width: THUMBNAIL_WIDTH, height: THUMBNAIL_HEIGHT }}
            >
              <FileThumbnail
                file={{ name: `${draggedPageId}.pdf`, type: "application/pdf" }}
                previewImageUrl={thumbnailImages[draggedPageId]}
                isLoading={!thumbnailImages[draggedPageId]}
                previewClassName="h-full aspect-auto"
                className="size-full rounded-[inherit] border-0 bg-transparent"
              />
            </div>
          ) : activeSplitGroup ? (
            <SplitGroupDragOverlay
              group={activeSplitGroup}
              thumbnailImages={thumbnailImages}
              width={activeSplitGroupWidth}
              onSelectPage={onSelectPage}
            />
          ) : null}
        </DragOverlay>
      </DndContext>
    </aside>
  );
}
function InlineScrollArea2({
  className,
  children,
  orientation = "both",
  scrollFade = false,
  scrollbarGutter = false,
  scrollbarOverflowOnly = false,
  viewportClassName,
  viewportProps,
  viewportRef,
  ...props
}: InlineScrollAreaProps) {
  const localViewportRef = React.useRef<HTMLDivElement>(null);
  const {
    className: viewportPropsClassName,
    ref: viewportPropsRef,
    style: viewportStyle,
    ...resolvedViewportProps
  } = viewportProps ?? {};
  const resolvedViewportStyle = { ...viewportStyle };
  delete resolvedViewportStyle.overflow;
  const composedViewportRef = React.useMemo(
    () => InlineComposeRefs(localViewportRef, viewportPropsRef, viewportRef),
    [viewportPropsRef, viewportRef]
  );

  React.useEffect(() => {
    const viewport = localViewportRef.current;
    if (!viewport || !scrollFade) return;
    const updateOverflow = () => {
      const x = Math.abs(viewport.scrollLeft);
      const y = Math.max(0, viewport.scrollTop);
      const overflow = {
        "x-start": x,
        "x-end": Math.max(0, viewport.scrollWidth - viewport.clientWidth - x),
        "y-start": y,
        "y-end": Math.max(0, viewport.scrollHeight - viewport.clientHeight - y),
      };
      for (const [edge, value] of Object.entries(overflow)) {
        viewport.style.setProperty(
          `--scroll-area-overflow-${edge}`,
          `${value}px`
        );
      }
    };
    const observer = new ResizeObserver(updateOverflow);
    observer.observe(viewport);
    if (viewport.firstElementChild)
      observer.observe(viewport.firstElementChild);
    viewport.addEventListener("scroll", updateOverflow, { passive: true });
    updateOverflow();
    return () => {
      observer.disconnect();
      viewport.removeEventListener("scroll", updateOverflow);
    };
  }, [scrollFade]);

  if (
    !viewportProps &&
    !viewportRef &&
    !viewportClassName &&
    !scrollFade &&
    !scrollbarGutter &&
    !scrollbarOverflowOnly
  ) {
    return (
      <InlineScrollArea
        {...props}
        className={cn(
          "size-full min-h-0",
          orientation === "horizontal" &&
            "[&>[data-orientation=vertical]]:hidden",
          className
        )}
      >
        {children}
        {orientation !== "vertical" ? (
          <ScrollBar orientation="horizontal" />
        ) : null}
      </InlineScrollArea>
    );
  }

  return (
    <ScrollAreaPrimitive.Root
      type={scrollbarOverflowOnly ? "auto" : "hover"}
      data-slot="scroll-area"
      className={cn("size-full min-h-0 overflow-hidden", className)}
      {...props}
    >
      <ScrollAreaPrimitive.Viewport
        {...resolvedViewportProps}
        style={resolvedViewportStyle}
        ref={composedViewportRef}
        data-slot="scroll-area-viewport"
        className={cn(
          "h-full w-full rounded-[inherit] outline-none focus-visible:ring-2 focus-visible:ring-oklch(0.708 0 0) dark:focus-visible:ring-oklch(0.556 0 0)",
          scrollFade &&
            "mask-t-from-[calc(100%-min(var(--fade-size),var(--scroll-area-overflow-y-start)))] mask-r-from-[calc(100%-min(var(--fade-size),var(--scroll-area-overflow-x-end)))] mask-b-from-[calc(100%-min(var(--fade-size),var(--scroll-area-overflow-y-end)))] mask-l-from-[calc(100%-min(var(--fade-size),var(--scroll-area-overflow-x-start)))] [--fade-size:1.5rem]",
          scrollbarGutter && orientation !== "vertical" && "pb-3.5",
          scrollbarGutter && orientation !== "horizontal" && "pe-3.5",
          viewportPropsClassName,
          viewportClassName
        )}
      >
        {children}
      </ScrollAreaPrimitive.Viewport>
      {orientation !== "horizontal" ? (
        <ScrollBar orientation="vertical" />
      ) : null}
      {orientation !== "vertical" ? (
        <ScrollBar orientation="horizontal" />
      ) : null}
      {orientation === "both" ? <ScrollAreaPrimitive.Corner /> : null}
    </ScrollAreaPrimitive.Root>
  );
}
type InlineScrollAreaProps = React.ComponentProps<
  typeof ScrollAreaPrimitive.Root
> & {
  orientation?: "vertical" | "horizontal" | "both";
  scrollFade?: boolean;
  scrollbarGutter?: boolean;
  scrollbarOverflowOnly?: boolean;
  viewportClassName?: string;
  viewportProps?: React.ComponentProps<typeof ScrollAreaPrimitive.Viewport>;
  viewportRef?: React.Ref<HTMLDivElement>;
};
function InlineComposeRefs<T>(...refs: Array<React.Ref<T> | undefined>) {
  return (node: T | null) => {
    for (const ref of refs) {
      if (!ref) continue;
      if (typeof ref === "function") ref(node);
      else ref.current = node;
    }
  };
}
