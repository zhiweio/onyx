"use client";

import { useTranslations } from "next-intl";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Button, Text } from "@opal/components";
import { SvgHandle, SvgEdit, SvgTrash, SvgArrowUp } from "@opal/icons";
import { cn } from "@opal/utils";

/**
 * QueuePanel — ZCode ConversationQueuePanel pattern for craft follow-ups:
 * drag-reorder, edit back into the composer, delete, and run-now, while the
 * existing FIFO auto-dequeue after a clean run stays owned by the chat panel.
 */

/** Any queue entry with an id and text; craft adds attachments/selection. */
interface QueueEntry {
  id: number;
  text: string;
}

interface QueuePanelProps<Message extends QueueEntry> {
  messages: readonly Message[];
  onReorder: (messages: Message[]) => void;
  onEdit: (message: Message) => void;
  onRemove: (index: number) => void;
  /** Sends a queued message immediately. */
  onRunNow: (message: Message, index: number) => void;
}

function QueueRow<Message extends QueueEntry>({
  message,
  index,
  onEdit,
  onRemove,
  onRunNow,
}: {
  message: Message;
  index: number;
  onEdit: QueuePanelProps<Message>["onEdit"];
  onRemove: QueuePanelProps<Message>["onRemove"];
  onRunNow: QueuePanelProps<Message>["onRunNow"];
}) {
  const t = useTranslations("craft.queuePanel");
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: message.id });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className="flex items-center gap-1 rounded-08 border border-border-01 bg-background-neutral-00 px-1.5 py-1"
      data-testid="craft-queue-row"
    >
      <button
        type="button"
        className="cursor-grab touch-none rounded-04 p-1 text-text-03 hover:bg-background-tint-02 active:cursor-grabbing"
        aria-label={t("dragHandle.ariaLabel")}
        {...attributes}
        {...listeners}
      >
        <SvgHandle className="size-4 stroke-text-03" />
      </button>
      <span className="min-w-0 flex-1 truncate">
        <Text font="secondary-body" color="text-04">
          {message.text}
        </Text>
      </span>
      <Button
        icon={SvgArrowUp}
        prominence="tertiary"
        tooltip={t("runNow.tooltip")}
        aria-label={t("runNow.tooltip")}
        onClick={() => onRunNow(message, index)}
      />
      <Button
        icon={SvgEdit}
        prominence="tertiary"
        tooltip={t("edit.tooltip")}
        aria-label={t("edit.tooltip")}
        onClick={() => onEdit(message)}
      />
      <Button
        icon={SvgTrash}
        prominence="tertiary"
        tooltip={t("remove.tooltip")}
        aria-label={t("remove.tooltip")}
        onClick={() => onRemove(index)}
      />
    </div>
  );
}

function QueuePanel<Message extends QueueEntry>({
  messages,
  onReorder,
  onEdit,
  onRemove,
  onRunNow,
}: QueuePanelProps<Message>) {
  const t = useTranslations("craft.queuePanel");
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }
    const from = messages.findIndex((message) => message.id === active.id);
    const to = messages.findIndex((message) => message.id === over.id);
    if (from < 0 || to < 0) {
      return;
    }
    onReorder(arrayMove(messages as Message[], from, to));
  };

  return (
    <div
      className={cn("flex flex-col gap-1 pb-2")}
      data-testid="craft-queue-panel"
    >
      <Text font="secondary-action" color="text-03">
        {t("header.title", { count: messages.length })}
      </Text>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={messages.map((message) => message.id)}
          strategy={verticalListSortingStrategy}
        >
          {messages.map((message, index) => (
            <QueueRow<Message>
              key={message.id}
              message={message}
              index={index}
              onEdit={onEdit}
              onRemove={onRemove}
              onRunNow={onRunNow}
            />
          ))}
        </SortableContext>
      </DndContext>
    </div>
  );
}

export default QueuePanel;
