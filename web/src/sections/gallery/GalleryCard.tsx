"use client";

import { useCallback, type MouseEvent } from "react";
import { useTranslations } from "next-intl";
import { Button, Tag } from "@opal/components";
import { Content } from "@opal/layouts";
import { SvgCopy, SvgZoomIn } from "@opal/icons";
import type { IconFunctionComponent } from "@opal/types";
import { Interactive } from "@opal/core";
import { CardItemLayout } from "@/layouts/general-layouts";
import { Card } from "@/refresh-components/cards";
import {
  categoryMessageKey,
  categoryTagColor,
  isDocxCatalogTemplate,
  type CatalogItem,
} from "@/lib/system-catalog/types";

export interface GalleryCardProps {
  item: CatalogItem;
  icon: IconFunctionComponent;
  onPreview?: (item: CatalogItem) => void;
  onFork?: (item: CatalogItem) => void;
  forking?: boolean;
  layout?: "card" | "row";
}

function stopAndCall(
  event: MouseEvent<HTMLElement>,
  handler: ((item: CatalogItem) => void) | undefined,
  item: CatalogItem,
) {
  event.stopPropagation();
  handler?.(item);
}

export default function GalleryCard({
  item,
  icon,
  onPreview,
  onFork,
  forking = false,
  layout = "card",
}: GalleryCardProps) {
  const t = useTranslations("craft.gallery");

  const handleClick = useCallback(() => {
    onPreview?.(item);
  }, [onPreview, item]);

  const actions = (
    <div className="flex items-center gap-1">
      <Button
        prominence="tertiary"
        size="sm"
        icon={SvgZoomIn}
        data-testid="GalleryCard/preview"
        tooltip={t("card.preview.tooltip")}
        aria-label={t("card.preview.tooltip")}
        onClick={(event) => stopAndCall(event, onPreview, item)}
      />
      <Button
        prominence="tertiary"
        size="sm"
        icon={SvgCopy}
        data-testid="GalleryCard/fork"
        disabled={forking}
        tooltip={t("card.fork.tooltip")}
        aria-label={t("card.fork.tooltip")}
        onClick={(event) => stopAndCall(event, onFork, item)}
      />
    </div>
  );

  const meta = (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1 px-1 py-1">
      <Tag
        size="sm"
        color={categoryTagColor(item.category)}
        title={t(categoryMessageKey(item.category))}
      />
      {isDocxCatalogTemplate(item) && (
        <span data-testid="GalleryCard/word">
          <Tag size="sm" color="green" title={t("card.kind.word.label")} />
        </span>
      )}
      <Content
        title={item.slug}
        sizePreset="secondary"
        variant="body"
        color="muted"
      />
      <Content
        title={t("card.version.label", { version: item.version })}
        sizePreset="secondary"
        variant="body"
        color="muted"
      />
    </div>
  );

  if (layout === "row") {
    return (
      <Interactive.Simple onClick={handleClick} group="group/GalleryCard">
        <Card variant="primary" padding={1} gap={0}>
          <div className="flex w-full flex-row items-center justify-between gap-2">
            <div className="min-w-0 flex-1">
              <Content
                icon={icon}
                title={item.name}
                description={item.description || item.slug}
                sizePreset="main-ui"
                variant="section"
              />
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {meta}
              {actions}
            </div>
          </div>
        </Card>
      </Interactive.Simple>
    );
  }

  return (
    <Interactive.Simple onClick={handleClick} group="group/GalleryCard">
      <Card variant="primary" padding={0} gap={0} height="full">
        <div className="flex self-stretch min-h-24">
          <CardItemLayout
            icon={icon}
            title={item.name}
            description={item.description || item.slug}
          />
        </div>
        <div className="bg-background-tint-01 p-1.5 flex flex-row items-center justify-between w-full">
          {meta}
          {actions}
        </div>
      </Card>
    </Interactive.Simple>
  );
}
