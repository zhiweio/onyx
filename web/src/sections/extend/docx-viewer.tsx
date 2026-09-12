"use client";

import * as React from "react";
import {
  DocxEditorViewer,
  useDocxComments,
  useDocxEditor,
  useDocxPageLayout,
  useDocxTrackChanges,
  useDocxViewerThumbnails,
  type DocxDocumentTheme,
  type DocxEditorController,
  type DocxPageThumbnailItem,
} from "@extend-ai/react-docx";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ScrollArea as ScrollAreaPrimitive } from "radix-ui";

import { cn } from "@/sections/extend/lib/utils";
import { Button } from "@/sections/extend/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/sections/extend/ui/dropdown-menu";
import { fileWithReadableDocxLineSpacing } from "@/sections/document-preview/prepareReadableDocxFile";
import "@/sections/document-preview/viewers/docx-host.css";
import { Input } from "@/sections/extend/ui/input";
import {
  ScrollArea as InlineScrollArea,
  ScrollBar,
} from "@/sections/extend/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/sections/extend/ui/select";
import { Separator } from "@/sections/extend/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/sections/extend/ui/tooltip";
import {
  DocumentViewerThumbnailSidebar,
  useElementWidth,
  useInlineThumbnailSidebar,
} from "@/sections/extend/document-viewer-sidebar";
import {
  createDocxCommentCardRenderer,
  createDocxTrackedChangeCardRenderer,
} from "@/sections/extend/docx-annotation-card";
import { FileThumbnail } from "@/sections/extend/file-thumbnail";
import { IconPlaceholder } from "@/sections/icon-placeholder";

const DOCX_MIME_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const DOCX_LOADING_INDICATOR_DELAY_MS = 300;
const DOCX_THUMBNAIL_WIDTH = 92;
const DOCX_THUMBNAIL_LIST_PADDING = 16;
const DOCX_THUMBNAIL_ROW_ESTIMATE = 172;
const DEFAULT_ZOOM = 50;
const ZOOM_OPTIONS = [10, 25, 50, 75, 100, 125, 150, 175, 200, 400] as const;
const DOCX_PADDING_WARNING_TEXT = "a style property during rerender";
const DOCX_THUMBNAIL_FOCUS_RING_CLASS =
  "group-focus-visible/docx-thumbnail-sidebar:ring-2 group-focus-visible/docx-thumbnail-sidebar:ring-oklch(0.708 0 0) group-focus-visible/docx-thumbnail-sidebar:ring-offset-1 group-focus-visible/docx-thumbnail-sidebar:ring-offset-oklch(1 0 0) dark:group-focus-visible/docx-thumbnail-sidebar:ring-oklch(0.556 0 0) dark:group-focus-visible/docx-thumbnail-sidebar:ring-offset-oklch(0.145 0 0)";
const DOCX_THUMBNAIL_PREFETCH_ROWS = 4;
type UploadedDocxFile = {
  file: File;
  identity: string;
  sourceUrl: string | undefined;
};
type DocxActivePageStore = {
  getSnapshot: () => number;
  setActivePage: React.Dispatch<React.SetStateAction<number>>;
  subscribe: (listener: () => void) => () => void;
};
type DocxThumbnailRenderWindowState = {
  visiblePageIndexes: number[];
  prefetchPageIndexes: number[];
};
function createDocxActivePageStore(): DocxActivePageStore {
  let activePage = 1;
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => activePage,
    setActivePage: (nextPage) => {
      const value =
        typeof nextPage === "function" ? nextPage(activePage) : nextPage;
      const normalizedValue = Math.max(1, Math.round(value || 1));
      if (normalizedValue === activePage) return;
      activePage = normalizedValue;
      listeners.forEach((listener) => listener());
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
function useDocxActivePage(activePageStore: DocxActivePageStore) {
  return React.useSyncExternalStore(
    activePageStore.subscribe,
    activePageStore.getSnapshot,
    activePageStore.getSnapshot
  );
}
function areNumberArraysEqual(left: number[], right: number[]) {
  return (
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}
async function loadDocxFile(
  url: string,
  displayFileName: string
): Promise<File> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch DOCX (${response.status})`);
  }
  const blob = await response.blob();
  return new File([blob], displayFileName, {
    type: blob.type || DOCX_MIME_TYPE,
  });
}
function formatDocumentName(fileName: string | undefined, url: string) {
  if (fileName?.trim()) return fileName;
  const pathname = url.split("?")[0] ?? "";
  const rawName = pathname.split("/").pop() ?? "document.docx";
  try {
    return decodeURIComponent(rawName);
  } catch {
    return rawName;
  }
}
function ensureDocxExtension(fileName: string) {
  return fileName.toLowerCase().endsWith(".docx")
    ? fileName
    : `${fileName}.docx`;
}
function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
async function downloadDocxFile({
  file,
  fileName,
  url,
}: {
  file?: File;
  fileName: string;
  url?: string;
}) {
  if (file) {
    downloadBlob(file, ensureDocxExtension(fileName));
    return;
  }
  if (!url) return;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download DOCX (${response.status})`);
  }
  downloadBlob(await response.blob(), ensureDocxExtension(fileName));
}
function getNextZoomScale(currentZoomScale: number, direction: 1 | -1) {
  const currentIndex = ZOOM_OPTIONS.indexOf(
    currentZoomScale as (typeof ZOOM_OPTIONS)[number]
  );
  let fallbackIndex = -1;
  if (direction > 0) {
    fallbackIndex = ZOOM_OPTIONS.findIndex((value) => value > currentZoomScale);
  } else {
    for (let index = ZOOM_OPTIONS.length - 1; index >= 0; index -= 1) {
      if (ZOOM_OPTIONS[index] < currentZoomScale) {
        fallbackIndex = index;
        break;
      }
    }
  }
  const resolvedIndex = currentIndex >= 0 ? currentIndex : fallbackIndex;
  if (resolvedIndex < 0) return currentZoomScale;
  const nextIndex = Math.min(
    Math.max(resolvedIndex + direction, 0),
    ZOOM_OPTIONS.length - 1
  );
  return ZOOM_OPTIONS[nextIndex] ?? currentZoomScale;
}
function normalizeDocxZoomScale(value: number | undefined): number {
  return typeof value === "number" &&
    ZOOM_OPTIONS.includes(value as (typeof ZOOM_OPTIONS)[number])
    ? value
    : DEFAULT_ZOOM;
}
function useDelayedLoadingIndicator(isLoading: boolean, delayMs: number) {
  const [showSpinner, setShowSpinner] = React.useState(false);
  const [previousIsLoading, setPreviousIsLoading] = React.useState(isLoading);
  if (previousIsLoading !== isLoading) {
    setPreviousIsLoading(isLoading);
    setShowSpinner(false);
  }
  React.useEffect(() => {
    if (!isLoading) return;
    const timeoutId = window.setTimeout(() => {
      setShowSpinner(true);
    }, delayMs);
    return () => window.clearTimeout(timeoutId);
  }, [delayMs, isLoading]);
  return isLoading && showSpinner;
}
function isDocxPaddingWarning(args: unknown[]) {
  return (
    typeof args[0] === "string" &&
    args[0].includes(DOCX_PADDING_WARNING_TEXT) &&
    args.some((arg) => String(arg).includes("padding"))
  );
}
function useSuppressDocxPaddingWarning(enabled: boolean) {
  React.useEffect(() => {
    if (!enabled) return;
    const originalConsoleError = console.error;
    console.error = (...args: unknown[]) => {
      if (isDocxPaddingWarning(args)) return;
      originalConsoleError(...args);
    };
    return () => {
      console.error = originalConsoleError;
    };
  }, [enabled]);
}
function isInteractiveViewerTarget(target: EventTarget | null) {
  return (
    target instanceof Element &&
    Boolean(
      target.closest(
        'a[href], button, input, select, textarea, [contenteditable="true"], [role="button"], [role="link"]'
      )
    )
  );
}
function ToolbarTooltip({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">{children}</span>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}
function ViewerLoadingSurface({
  showSpinner = true,
}: {
  showSpinner?: boolean;
}) {
  return (
    <div className="grid h-full min-h-52 place-items-center bg-transparent">
      {showSpinner ? <InlineSpinner className="size-4" /> : null}
    </div>
  );
}
function ActionsMenuToggleItem({
  checked,
  disabled,
  icon,
  label,
  onCheckedChange,
}: {
  checked: boolean;
  disabled?: boolean;
  icon: React.ReactNode;
  label: string;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <DropdownMenuItem
      disabled={disabled}
      aria-checked={checked}
      onSelect={(event) => {
        event.preventDefault();
        onCheckedChange(!checked);
      }}
    >
      {icon}
      <span className="flex-1">{label}</span>
      {checked ? (
        <IconPlaceholder
          lucide="Check"
          tabler="IconCheck"
          hugeicons="Tick02Icon"
          phosphor="CheckIcon"
          remixicon="RiCheckLine"
          className="size-4 opacity-70"
        />
      ) : (
        <span className="size-4" aria-hidden />
      )}
    </DropdownMenuItem>
  );
}
function DocxDownloadButton({
  disabled,
  isPreparing,
  onDownload,
}: {
  disabled: boolean;
  isPreparing: boolean;
  onDownload: () => void;
}) {
  return (
    <ToolbarTooltip label="Download">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        disabled={disabled}
        aria-label="Download"
        onClick={onDownload}
      >
        {isPreparing ? (
          <InlineSpinner className="size-4" />
        ) : (
          <IconPlaceholder
            lucide="Download"
            tabler="IconDownload"
            hugeicons="Download01Icon"
            phosphor="DownloadSimpleIcon"
            remixicon="RiDownload2Line"
            className="size-4"
          />
        )}
      </Button>
    </ToolbarTooltip>
  );
}
function DocxFileActionsMenu({
  controlsDisabled,
  downloadDisabled,
  isPreparingDownload,
  isDark,
  onDownload,
  onShowCommentsChange,
  onShowTrackedChangesChange,
  onIsDarkChange,
  onUploadClick,
  showComments,
  showDownloadButton,
  showNightRenderToggle,
  showReviewControls,
  showTrackedChanges,
  showUploadButton,
}: {
  controlsDisabled: boolean;
  downloadDisabled: boolean;
  isPreparingDownload: boolean;
  isDark: boolean;
  onDownload: () => void;
  onShowCommentsChange: (checked: boolean) => void;
  onShowTrackedChangesChange: (checked: boolean) => void;
  onIsDarkChange: (checked: boolean) => void;
  onUploadClick: () => void;
  showComments: boolean;
  showDownloadButton: boolean;
  showNightRenderToggle: boolean;
  showReviewControls: boolean;
  showTrackedChanges: boolean;
  showUploadButton: boolean;
}) {
  const showFileActions = showDownloadButton || showUploadButton;
  const showMenu =
    showNightRenderToggle || showReviewControls || showFileActions;
  if (!showMenu) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Open document actions"
        >
          <IconPlaceholder
            lucide="Ellipsis"
            tabler="IconDots"
            hugeicons="MoreHorizontalIcon"
            phosphor="DotsThreeIcon"
            remixicon="RiMoreLine"
            className="size-4"
          />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        {showNightRenderToggle ? (
          <ActionsMenuToggleItem
            checked={isDark}
            disabled={controlsDisabled}
            label="Dark mode"
            onCheckedChange={onIsDarkChange}
            icon={
              <IconPlaceholder
                lucide="Moon"
                tabler="IconMoon"
                hugeicons="Moon02Icon"
                phosphor="MoonIcon"
                remixicon="RiMoonLine"
                className="size-4"
              />
            }
          />
        ) : null}
        {showReviewControls ? (
          <>
            <ActionsMenuToggleItem
              checked={showComments}
              disabled={controlsDisabled}
              label="Comments"
              onCheckedChange={onShowCommentsChange}
              icon={
                <IconPlaceholder
                  lucide="MessageSquare"
                  tabler="IconMessage"
                  hugeicons="Comment01Icon"
                  phosphor="ChatIcon"
                  remixicon="RiChat1Line"
                  className="size-4"
                />
              }
            />
            <ActionsMenuToggleItem
              checked={showTrackedChanges}
              disabled={controlsDisabled}
              label="Edits"
              onCheckedChange={onShowTrackedChangesChange}
              icon={
                <IconPlaceholder
                  lucide="FileDiff"
                  tabler="IconFileDiff"
                  hugeicons="FileDiffIcon"
                  phosphor="GitDiffIcon"
                  remixicon="RiFileHistoryLine"
                  className="size-4"
                />
              }
            />
          </>
        ) : null}
        {showFileActions && (showNightRenderToggle || showReviewControls) ? (
          <DropdownMenuSeparator />
        ) : null}
        {showDownloadButton ? (
          <DropdownMenuItem disabled={downloadDisabled} onClick={onDownload}>
            {isPreparingDownload ? (
              <InlineSpinner className="size-4" />
            ) : (
              <IconPlaceholder
                lucide="Download"
                tabler="IconDownload"
                hugeicons="Download01Icon"
                phosphor="DownloadSimpleIcon"
                remixicon="RiDownload2Line"
                className="size-4 shrink-0"
              />
            )}
            <span>Download</span>
          </DropdownMenuItem>
        ) : null}
        {showUploadButton ? (
          <DropdownMenuItem onClick={onUploadClick}>
            <IconPlaceholder
              lucide="Upload"
              tabler="IconUpload"
              hugeicons="Upload01Icon"
              phosphor="UploadSimpleIcon"
              remixicon="RiUpload2Line"
              className="size-4"
            />
            <span>Upload</span>
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
function DocxPageNumberControl({
  activePageStore,
  controlsDisabled,
  onPageChange,
  pageCount,
}: {
  activePageStore: DocxActivePageStore;
  controlsDisabled: boolean;
  onPageChange: (pageNumber: number) => void;
  pageCount: number;
}) {
  const activePage = useDocxActivePage(activePageStore);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const displayPage = pageCount ? activePage : 1;
  const [isEditing, setIsEditing] = React.useState(false);
  const [draftPage, setDraftPage] = React.useState(() => String(displayPage));
  React.useEffect(() => {
    if (!isEditing) return;
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [isEditing]);
  const applyPageDraft = React.useCallback(
    (value: string) => {
      const trimmedValue = value.trim();
      if (!trimmedValue) return;
      const parsedPage = Number(trimmedValue);
      if (!Number.isInteger(parsedPage)) return;
      onPageChange(Math.min(Math.max(parsedPage, 1), Math.max(pageCount, 1)));
    },
    [onPageChange, pageCount]
  );
  return (
    <div className="flex items-center text-sm whitespace-nowrap text-oklch(0.205 0 0) dark:text-oklch(0.922 0 0)">
      <span>Page</span>
      {isEditing ? (
        <Input
          ref={inputRef}
          aria-label="Page number"
          inputMode="numeric"
          pattern="[0-9]*"
          value={draftPage}
          onBlur={() => setIsEditing(false)}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
            const nextValue = event.target.value;
            setDraftPage(nextValue);
            applyPageDraft(nextValue);
          }}
          onKeyDown={(event: React.KeyboardEvent<HTMLInputElement>) => {
            if (event.key === "Enter" || event.key === "Escape") {
              event.currentTarget.blur();
            }
          }}
          className={cn(
            "h-8 px-2.5",
            "mx-1 w-14 min-w-14 rounded-md [&_[data-slot=input]]:text-center"
          )}
        />
      ) : (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="font-normal"
          aria-label={`Current page ${displayPage}. Edit page number`}
          disabled={controlsDisabled || !pageCount}
          onClick={() => {
            setDraftPage(String(displayPage));
            setIsEditing(true);
          }}
        >
          {displayPage}
        </Button>
      )}
      <span>of {pageCount || "-"}</span>
    </div>
  );
}
function DocxToolbar({
  activePageStore,
  controlsDisabled,
  isDark,
  isPreparingDownload,
  onDownload,
  onIsDarkChange,
  onPageChange,
  onShowCommentsChange,
  onShowTrackedChangesChange,
  onToggleSidebar,
  onUploadClick,
  pageCount,
  setZoomScale,
  showComments,
  showDownloadButton = true,
  showNightRenderToggle,
  showReviewControls = false,
  showTrackedChanges,
  showUploadButton = true,
  toolbarActions,
  zoomScale,
}: {
  activePageStore: DocxActivePageStore;
  controlsDisabled: boolean;
  isDark: boolean;
  isPreparingDownload: boolean;
  onDownload: () => void;
  onIsDarkChange: (checked: boolean) => void;
  onPageChange: (pageNumber: number) => void;
  onShowCommentsChange: (checked: boolean) => void;
  onShowTrackedChangesChange: (checked: boolean) => void;
  onToggleSidebar: () => void;
  onUploadClick: () => void;
  pageCount: number;
  setZoomScale: React.Dispatch<React.SetStateAction<number>>;
  showComments: boolean;
  showDownloadButton?: boolean;
  showNightRenderToggle: boolean;
  showReviewControls?: boolean;
  showTrackedChanges: boolean;
  showUploadButton?: boolean;
  toolbarActions?: React.ReactNode;
  zoomScale: number;
}) {
  const canZoomIn = zoomScale < ZOOM_OPTIONS[ZOOM_OPTIONS.length - 1];
  const canZoomOut = zoomScale > ZOOM_OPTIONS[0];
  const downloadOnly =
    showDownloadButton &&
    !showNightRenderToggle &&
    !showReviewControls &&
    !showUploadButton;
  const showDocumentActions =
    showDownloadButton ||
    showUploadButton ||
    showNightRenderToggle ||
    showReviewControls;
  return (
    <div className="flex min-h-12 flex-wrap items-center justify-between gap-2 border-b bg-oklch(1 0 0) px-3 py-2 dark:bg-oklch(0.145 0 0)">
      <TooltipProvider>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <ToolbarTooltip label="Toggle thumbnails">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Toggle thumbnails"
              disabled={controlsDisabled}
              onClick={onToggleSidebar}
            >
              <IconPlaceholder
                lucide="PanelLeft"
                tabler="IconLayoutSidebar"
                hugeicons="SidebarLeftIcon"
                phosphor="SidebarIcon"
                remixicon="RiLayoutLeftLine"
                className="size-4"
              />
            </Button>
          </ToolbarTooltip>
          <DocxPageNumberControl
            activePageStore={activePageStore}
            controlsDisabled={controlsDisabled}
            onPageChange={onPageChange}
            pageCount={pageCount}
          />
        </div>
        <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-1">
          <div className="flex flex-none items-center gap-1">
            <ToolbarTooltip label="Zoom out">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                disabled={controlsDisabled || !canZoomOut}
                aria-label="Zoom out"
                onClick={() =>
                  setZoomScale((currentZoomScale) =>
                    getNextZoomScale(currentZoomScale, -1)
                  )
                }
              >
                <IconPlaceholder
                  lucide="CircleMinus"
                  tabler="IconCircleMinus"
                  hugeicons="MinusSignCircleIcon"
                  phosphor="MinusCircleIcon"
                  remixicon="RiIndeterminateCircleLine"
                  className="size-4"
                />
              </Button>
            </ToolbarTooltip>
            <Select
              value={zoomScale.toString()}
              onValueChange={(value) => setZoomScale(Number(value))}
              disabled={controlsDisabled}
            >
              <SelectTrigger
                size="sm"
                className="w-[84px] min-w-[84px]"
                aria-label="Zoom level"
              >
                <SelectValue>{Math.round(zoomScale)}%</SelectValue>
              </SelectTrigger>
              <SelectContent
                align="end"
                position={false ? "item-aligned" : "popper"}
              >
                {ZOOM_OPTIONS.map((value) => (
                  <SelectItem key={value} value={value.toString()}>
                    {value}%
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ToolbarTooltip label="Zoom in">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                disabled={controlsDisabled || !canZoomIn}
                aria-label="Zoom in"
                onClick={() =>
                  setZoomScale((currentZoomScale) =>
                    getNextZoomScale(currentZoomScale, 1)
                  )
                }
              >
                <IconPlaceholder
                  lucide="CirclePlusIcon"
                  tabler="IconCirclePlusFilled"
                  hugeicons="PlusSignCircleIcon"
                  phosphor="PlusCircleIcon"
                  remixicon="RiAddCircleFill"
                  className="size-4"
                />
              </Button>
            </ToolbarTooltip>
          </div>
          {toolbarActions ? (
            <>
              <Separator
                orientation="vertical"
                className="mx-1 h-4 self-center"
              />
              {toolbarActions}
            </>
          ) : null}
          {showDocumentActions ? (
            <>
              <Separator
                orientation="vertical"
                className="mx-1 h-4 self-center"
              />
              {downloadOnly ? (
                <DocxDownloadButton
                  disabled={controlsDisabled || isPreparingDownload}
                  isPreparing={isPreparingDownload}
                  onDownload={onDownload}
                />
              ) : (
                <DocxFileActionsMenu
                  controlsDisabled={controlsDisabled}
                  downloadDisabled={controlsDisabled || isPreparingDownload}
                  isPreparingDownload={isPreparingDownload}
                  isDark={isDark}
                  onDownload={onDownload}
                  onIsDarkChange={onIsDarkChange}
                  onShowCommentsChange={onShowCommentsChange}
                  onShowTrackedChangesChange={onShowTrackedChangesChange}
                  onUploadClick={onUploadClick}
                  showComments={showComments}
                  showDownloadButton={showDownloadButton}
                  showNightRenderToggle={showNightRenderToggle}
                  showReviewControls={showReviewControls}
                  showTrackedChanges={showTrackedChanges}
                  showUploadButton={showUploadButton}
                />
              )}
            </>
          ) : null}
        </div>
      </TooltipProvider>
    </div>
  );
}
function DocxSidebarThumbnail({
  canvasRef,
  displayFileName,
  hasError,
  isActive,
  isLoading,
  pageNumber,
  pixelHeightPx,
  pixelWidthPx,
  previewAspectRatio,
}: {
  canvasRef: React.RefCallback<HTMLCanvasElement>;
  displayFileName: string;
  hasError: boolean;
  isActive: boolean;
  isLoading: boolean;
  pageNumber: number;
  pixelHeightPx: number;
  pixelWidthPx: number;
  previewAspectRatio: number;
}) {
  return (
    <FileThumbnail
      file={{
        name: `${displayFileName} page ${pageNumber}`,
        type: DOCX_MIME_TYPE,
      }}
      previewAspectRatio={previewAspectRatio}
      previewClassName="rounded-md bg-white"
      previewContent={
        <canvas
          ref={canvasRef}
          width={pixelWidthPx}
          height={pixelHeightPx}
          className="!size-full bg-white object-cover object-top"
        />
      }
      isLoading={isLoading}
      hasError={hasError}
      className={cn(
        "w-[92px] rounded-md border-0 shadow-xs ring-0 transition-shadow duration-150",
        isActive && "shadow-sm"
      )}
    />
  );
}
function DocxThumbnailSidebarList({
  activePage,
  displayFileName,
  isLoadingDocument,
  onSelectPage,
  onThumbnailRenderWindowChange,
  pageCount,
  sidebarOpen,
  thumbnails,
}: {
  activePage: number;
  displayFileName: string;
  isLoadingDocument: boolean;
  onSelectPage: (pageNumber: number) => void;
  onThumbnailRenderWindowChange: (
    renderWindow: DocxThumbnailRenderWindowState
  ) => void;
  pageCount: number;
  sidebarOpen: boolean;
  thumbnails: DocxPageThumbnailItem[];
}) {
  const viewportRef = React.useRef<HTMLDivElement | null>(null);
  const thumbnailListboxId = React.useId();
  const visibleThumbnails = React.useMemo(
    () => thumbnails.slice(0, pageCount || 0),
    [pageCount, thumbnails]
  );
  const activeDescendantId =
    activePage > 0 && visibleThumbnails.length
      ? `${thumbnailListboxId}-page-${activePage}`
      : undefined;
  const virtualizer = useVirtualizer({
    count: visibleThumbnails.length,
    estimateSize: () => DOCX_THUMBNAIL_ROW_ESTIMATE,
    getItemKey: (index) => visibleThumbnails[index]?.pageIndex ?? index,
    getScrollElement: () => viewportRef.current,
    overscan: 3,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const renderWindowSignature = virtualItems
    .map((virtualRow) => virtualRow.index)
    .join(",");
  React.useEffect(() => {
    if (!sidebarOpen || isLoadingDocument || !visibleThumbnails.length) {
      onThumbnailRenderWindowChange({
        prefetchPageIndexes: [],
        visiblePageIndexes: [],
      });
      return;
    }
    const visiblePageIndexes = virtualItems
      .map((virtualRow) => visibleThumbnails[virtualRow.index]?.pageIndex)
      .filter((pageIndex): pageIndex is number => pageIndex !== undefined);
    const firstVirtualIndex = virtualItems[0]?.index ?? 0;
    const lastVirtualIndex =
      virtualItems[virtualItems.length - 1]?.index ?? firstVirtualIndex;
    const firstPrefetchIndex = Math.max(
      0,
      firstVirtualIndex - DOCX_THUMBNAIL_PREFETCH_ROWS
    );
    const lastPrefetchIndex = Math.min(
      visibleThumbnails.length - 1,
      lastVirtualIndex + DOCX_THUMBNAIL_PREFETCH_ROWS
    );
    const visiblePageIndexSet = new Set(visiblePageIndexes);
    const prefetchPageIndexes: number[] = [];
    for (
      let index = firstPrefetchIndex;
      index <= lastPrefetchIndex;
      index += 1
    ) {
      const pageIndex = visibleThumbnails[index]?.pageIndex;
      if (pageIndex !== undefined && !visiblePageIndexSet.has(pageIndex)) {
        prefetchPageIndexes.push(pageIndex);
      }
    }
    onThumbnailRenderWindowChange({
      prefetchPageIndexes,
      visiblePageIndexes,
    });
  }, [
    isLoadingDocument,
    onThumbnailRenderWindowChange,
    renderWindowSignature,
    sidebarOpen,
    visibleThumbnails,
    virtualItems,
  ]);
  React.useEffect(() => {
    if (!sidebarOpen || activePage < 1 || !visibleThumbnails.length) return;
    virtualizer.scrollToIndex(
      Math.min(activePage - 1, visibleThumbnails.length - 1),
      { align: "auto" }
    );
  }, [activePage, sidebarOpen, virtualizer, visibleThumbnails.length]);
  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (pageCount < 1) return;
      const currentPage = activePage > 0 ? activePage : 1;
      let nextPage: number | null = null;
      if (event.key === "ArrowDown") {
        nextPage = Math.min(pageCount, currentPage + 1);
      } else if (event.key === "ArrowUp") {
        nextPage = Math.max(1, currentPage - 1);
      } else if (event.key === "Home") {
        nextPage = 1;
      } else if (event.key === "End") {
        nextPage = pageCount;
      }
      if (nextPage === null) return;
      event.preventDefault();
      onSelectPage(nextPage);
    },
    [activePage, onSelectPage, pageCount]
  );
  return (
    <InlineScrollArea2
      className="h-full"
      scrollFade
      viewportClassName="group/docx-thumbnail-sidebar focus-visible:ring-0 focus-visible:ring-offset-0"
      viewportProps={{
        "aria-activedescendant": activeDescendantId,
        "aria-busy": isLoadingDocument || undefined,
        "aria-label": "DOCX pages",
        onKeyDown: handleKeyDown,
        onMouseDown: (event) => {
          event.currentTarget.focus({ preventScroll: true });
        },
        role: "listbox",
        tabIndex: 0,
      }}
      viewportRef={viewportRef}
    >
      {isLoadingDocument ? (
        <div className="p-4">
          <div className="mx-auto h-28 w-20 overflow-hidden rounded-md bg-oklch(1 0 0) shadow-xs dark:bg-oklch(0.145 0 0)">
            <div className="h-full animate-pulse bg-oklch(0.97 0 0) dark:bg-oklch(0.269 0 0)" />
          </div>
          <div className="mx-auto mt-3 h-3 w-10 rounded-full bg-oklch(0.97 0 0) dark:bg-oklch(0.269 0 0)" />
        </div>
      ) : visibleThumbnails.length ? (
        <div
          className="relative"
          style={{
            height:
              virtualizer.getTotalSize() + DOCX_THUMBNAIL_LIST_PADDING * 2,
          }}
        >
          {virtualItems.map((virtualRow) => {
            const thumbnail = visibleThumbnails[virtualRow.index];
            if (!thumbnail) return null;
            return (
              <div
                key={virtualRow.key}
                ref={virtualizer.measureElement}
                data-index={virtualRow.index}
                className={cn(
                  "absolute top-0 right-3 left-3 pb-3 [contain:layout]",
                  thumbnail.pageNumber === activePage && "z-10"
                )}
                style={{
                  transform: `translateY(${virtualRow.start + DOCX_THUMBNAIL_LIST_PADDING}px)`,
                }}
              >
                <div
                  id={`${thumbnailListboxId}-page-${thumbnail.pageNumber}`}
                  role="option"
                  aria-current={
                    thumbnail.pageNumber === activePage ? "page" : undefined
                  }
                  aria-label={`Page ${thumbnail.pageNumber}`}
                  aria-posinset={thumbnail.pageNumber}
                  aria-selected={thumbnail.pageNumber === activePage}
                  aria-setsize={pageCount}
                  data-docx-viewer-thumbnail-option={thumbnail.pageNumber}
                  className={cn(
                    "flex h-auto w-full cursor-default flex-col items-center gap-2 rounded-md p-2 text-xs transition-shadow outline-none select-none hover:bg-oklch(0.97 0 0) dark:hover:bg-oklch(0.269 0 0)",
                    thumbnail.pageNumber === activePage &&
                      "bg-oklch(0.97 0 0) text-oklch(0.145 0 0) dark:bg-oklch(0.269 0 0) dark:text-oklch(0.985 0 0)",
                    thumbnail.pageNumber !== activePage &&
                      "text-oklch(0.556 0 0) dark:text-oklch(0.708 0 0)",
                    thumbnail.pageNumber === activePage &&
                      DOCX_THUMBNAIL_FOCUS_RING_CLASS
                  )}
                  onClick={() => onSelectPage(thumbnail.pageNumber)}
                >
                  <DocxSidebarThumbnail
                    canvasRef={thumbnail.canvasRef}
                    displayFileName={displayFileName}
                    hasError={thumbnail.status === "error"}
                    isActive={thumbnail.pageNumber === activePage}
                    isLoading={
                      thumbnail.status !== "ready" &&
                      thumbnail.status !== "error"
                    }
                    pageNumber={thumbnail.pageNumber}
                    pixelHeightPx={thumbnail.pixelHeightPx}
                    pixelWidthPx={thumbnail.pixelWidthPx}
                    previewAspectRatio={thumbnail.aspectRatio}
                  />
                  {thumbnail.pageNumber}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </InlineScrollArea2>
  );
}
function DocxThumbnailSidebarContent({
  activePageStore,
  displayFileName,
  editor,
  isLoadingDocument,
  onSelectPage,
  pageCount,
  reportedPageCount,
  sidebarOpen,
}: {
  activePageStore: DocxActivePageStore;
  displayFileName: string;
  editor: DocxEditorController;
  isLoadingDocument: boolean;
  onSelectPage: (pageNumber: number) => void;
  pageCount: number;
  reportedPageCount: number;
  sidebarOpen: boolean;
}) {
  const [thumbnailRenderWindow, setThumbnailRenderWindow] =
    React.useState<DocxThumbnailRenderWindowState>({
      prefetchPageIndexes: [],
      visiblePageIndexes: [],
    });
  const thumbnailEditor = React.useMemo<DocxEditorController>(
    () => ({
      ...editor,
      totalPages: Math.max(editor.totalPages, reportedPageCount),
    }),
    [editor, reportedPageCount]
  );
  const thumbnailOptions = React.useMemo(
    () => ({
      // Detached thumbnail rendering handles offscreen pages; keep the raster
      // queue dormant while the sidebar is closed.
      disabled: !sidebarOpen,
      pixelRatio: 2,
      renderWindow: thumbnailRenderWindow,
      resolution: {
        maxHeight: DOCX_THUMBNAIL_WIDTH * 1.35,
        maxWidth: DOCX_THUMBNAIL_WIDTH,
      },
    }),
    [sidebarOpen, thumbnailRenderWindow]
  );
  const { thumbnails } = useDocxViewerThumbnails(
    thumbnailEditor,
    thumbnailOptions
  );
  const activePage = useDocxActivePage(activePageStore);
  const handleThumbnailRenderWindowChange = React.useCallback(
    (nextRenderWindow: DocxThumbnailRenderWindowState) => {
      setThumbnailRenderWindow((currentRenderWindow) => {
        if (
          areNumberArraysEqual(
            currentRenderWindow.visiblePageIndexes,
            nextRenderWindow.visiblePageIndexes
          ) &&
          areNumberArraysEqual(
            currentRenderWindow.prefetchPageIndexes,
            nextRenderWindow.prefetchPageIndexes
          )
        ) {
          return currentRenderWindow;
        }
        return nextRenderWindow;
      });
    },
    []
  );
  if (!sidebarOpen) return null;
  return (
    <DocxThumbnailSidebarList
      activePage={activePage}
      displayFileName={displayFileName}
      isLoadingDocument={isLoadingDocument}
      onSelectPage={onSelectPage}
      onThumbnailRenderWindowChange={handleThumbnailRenderWindowChange}
      pageCount={pageCount}
      sidebarOpen={sidebarOpen}
      thumbnails={thumbnails}
    />
  );
}
export function DocxViewerPreview({
  className,
  defaultZoom = DEFAULT_ZOOM,
  fileName,
  isDark,
  onIsDarkChange,
  showDownload = true,
  showNightRenderToggle = false,
  showToolbar = true,
  showUpload = true,
  src,
  toolbarActions,
}: {
  className?: string;
  defaultZoom?: number;
  fileName?: string;
  isDark: boolean;
  onIsDarkChange: (isDark: boolean) => void;
  showDownload?: boolean;
  showNightRenderToggle?: boolean;
  showToolbar?: boolean;
  showUpload?: boolean;
  src?: string;
  toolbarActions?: React.ReactNode;
}) {
  return (
    <DocxViewerContent
      className={className}
      defaultZoom={defaultZoom}
      effectiveIsDark={showNightRenderToggle && isDark}
      fileName={fileName}
      setNightRenderEnabled={onIsDarkChange}
      shouldRenderNightMode={showNightRenderToggle}
      showDownload={showDownload}
      showToolbar={showToolbar}
      showUpload={showUpload}
      toolbarActions={toolbarActions}
      url={src}
    />
  );
}
function DocxViewerContent({
  className,
  defaultZoom,
  effectiveIsDark,
  fileName,
  setNightRenderEnabled,
  shouldRenderNightMode,
  showDownload,
  showToolbar = true,
  showUpload,
  toolbarActions,
  url,
}: {
  className?: string;
  defaultZoom?: number;
  effectiveIsDark: boolean;
  fileName?: string;
  setNightRenderEnabled: (checked: boolean) => void;
  shouldRenderNightMode: boolean;
  showDownload: boolean;
  showToolbar?: boolean;
  showUpload: boolean;
  toolbarActions?: React.ReactNode;
  url?: string;
}) {
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const viewportRef = React.useRef<HTMLDivElement | null>(null);
  const [viewportElement, setViewportElement] =
    React.useState<HTMLDivElement | null>(null);
  const [viewerShellRef, viewerShellWidth] = useElementWidth<HTMLDivElement>();
  const [uploadedDocxFile, setUploadedDocxFile] =
    React.useState<UploadedDocxFile | null>(null);
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const activePageStore = React.useMemo(() => createDocxActivePageStore(), []);
  const resolvedDefaultZoomScale = normalizeDocxZoomScale(defaultZoom);
  const activeUploadedDocxFile =
    uploadedDocxFile?.sourceUrl === url ? uploadedDocxFile : null;
  const documentKey = activeUploadedDocxFile?.identity ?? url ?? "";
  const setActivePage = activePageStore.setActivePage;
  const sidebarInline = useInlineThumbnailSidebar(viewerShellWidth);
  const viewerBackgroundColor =
    "color-mix(in oklab, var(--muted) 40%, transparent)";
  const displayFileName = React.useMemo(
    () =>
      activeUploadedDocxFile?.file.name ??
      (url ? formatDocumentName(fileName, url) : (fileName ?? "document.docx")),
    [activeUploadedDocxFile?.file.name, fileName, url]
  );
  const [initialDocumentTheme] = React.useState<DocxDocumentTheme>(() =>
    effectiveIsDark ? "dark" : "light"
  );
  const editorOptions = React.useMemo(
    () => ({
      initialDocumentTheme,
      initialFileName: displayFileName,
    }),
    [displayFileName, initialDocumentTheme]
  );
  const editor = useDocxEditor(editorOptions);
  const { layout: pageLayout } = useDocxPageLayout(editor);
  const { importDocxFile, setDocumentTheme, status } = editor;
  const { showComments, setShowComments } = useDocxComments(editor);
  const { showTrackedChanges, setShowTrackedChanges } =
    useDocxTrackChanges(editor);
  const [reportedPageCount, setReportedPageCount] = React.useState(0);
  const [zoomScaleState, setZoomScaleState] = React.useState({
    documentKey: "",
    value: resolvedDefaultZoomScale,
  });
  const zoomScale =
    zoomScaleState.documentKey === documentKey
      ? zoomScaleState.value
      : resolvedDefaultZoomScale;
  const setZoomScale = React.useCallback<
    React.Dispatch<React.SetStateAction<number>>
  >(
    (nextZoomScale) => {
      setZoomScaleState((currentState) => {
        const currentZoomScale =
          currentState.documentKey === documentKey
            ? currentState.value
            : resolvedDefaultZoomScale;
        const value =
          typeof nextZoomScale === "function"
            ? nextZoomScale(currentZoomScale)
            : nextZoomScale;
        return { documentKey, value };
      });
    },
    [documentKey, resolvedDefaultZoomScale]
  );
  const [loadError, setLoadError] = React.useState<string>();
  const [isLoadingDocument, setIsLoadingDocument] = React.useState(true);
  const [isPreparingDownload, setIsPreparingDownload] = React.useState(false);
  const shouldShowDocumentSpinner = useDelayedLoadingIndicator(
    isLoadingDocument,
    DOCX_LOADING_INDICATOR_DELAY_MS
  );
  const loadingState = (
    <ViewerLoadingSurface showSpinner={shouldShowDocumentSpinner} />
  );
  const documentTheme = effectiveIsDark ? "dark" : "light";
  const renderTrackedChangeCard = React.useMemo(
    () => createDocxTrackedChangeCardRenderer(documentTheme),
    [documentTheme]
  );
  const renderCommentCard = React.useMemo(
    () => createDocxCommentCardRenderer(documentTheme),
    [documentTheme]
  );
  const hasDocument = Boolean(url || activeUploadedDocxFile);
  const pageCount =
    hasDocument && !isLoadingDocument && !loadError
      ? Math.max(1, reportedPageCount || editor.totalPages)
      : 0;
  const thumbnailSidebarVisible = Boolean(
    sidebarOpen && (pageCount || isLoadingDocument)
  );
  const controlsDisabled =
    !hasDocument || isLoadingDocument || Boolean(loadError);
  const handlePageCountChange = React.useCallback((nextPageCount: number) => {
    setReportedPageCount(Math.max(1, Math.round(nextPageCount || 1)));
  }, []);
  const setViewportRef = React.useCallback((element: HTMLDivElement | null) => {
    viewportRef.current = element;
    setViewportElement(element);
  }, []);
  const pageVirtualization = React.useMemo(
    () => ({
      enabled: true,
      overscan: 1,
      scrollElement: viewportElement,
      zoomScale: zoomScale / 100,
    }),
    [viewportElement, zoomScale]
  );
  const handleDownload = React.useCallback(async () => {
    if (isPreparingDownload) return;
    if (!activeUploadedDocxFile && !url) return;
    setIsPreparingDownload(true);
    try {
      await downloadDocxFile({
        file: activeUploadedDocxFile?.file,
        fileName: displayFileName,
        url,
      });
    } catch (error) {
      console.error(error);
    } finally {
      setIsPreparingDownload(false);
    }
  }, [activeUploadedDocxFile, displayFileName, isPreparingDownload, url]);
  useSuppressDocxPaddingWarning(!isLoadingDocument && !loadError);
  React.useEffect(() => {
    setActivePage(1);
    viewportRef.current?.scrollTo({ top: 0, left: 0 });
  }, [documentKey, setActivePage]);
  React.useEffect(() => {
    setDocumentTheme(effectiveIsDark ? "dark" : "light");
  }, [effectiveIsDark, setDocumentTheme]);
  React.useEffect(() => {
    if (
      status.startsWith("Failed to load file") ||
      status === "Only .docx files are supported"
    ) {
      const frame = window.requestAnimationFrame(() => {
        setLoadError(status);
        setIsLoadingDocument(false);
      });
      return () => window.cancelAnimationFrame(frame);
    }
  }, [status]);
  // Imports mutate the shared editor instance; concurrent calls (effect
  // re-runs, StrictMode double-invoke) race inside the parser and surface as
  // bogus "Invalid DOCX ZIP" errors, so every import is chained through here.
  const importQueueRef = React.useRef<Promise<void>>(Promise.resolve());
  React.useEffect(() => {
    let isCurrent = true;
    async function load() {
      // Superseded while queued — let the newest import run instead.
      if (!isCurrent) return;
      if (!activeUploadedDocxFile && !url) {
        setIsLoadingDocument(false);
        setLoadError(undefined);
        setReportedPageCount(0);
        return;
      }
      setIsLoadingDocument(true);
      setLoadError(undefined);
      setReportedPageCount(0);
      try {
        const rawDocxFile =
          activeUploadedDocxFile?.file ??
          (url ? await loadDocxFile(url, displayFileName) : null);
        if (!rawDocxFile) return;
        await importDocxFile(
          await fileWithReadableDocxLineSpacing(rawDocxFile)
        );
        if (isCurrent) {
          setIsLoadingDocument(false);
          setActivePage(1);
          viewportRef.current?.scrollTo({ top: 0, left: 0 });
        }
      } catch (error) {
        if (isCurrent) {
          setLoadError(
            error instanceof Error ? error.message : "Unknown DOCX load error"
          );
          setIsLoadingDocument(false);
        }
      }
    }
    importQueueRef.current = importQueueRef.current.then(load);
    return () => {
      isCurrent = false;
    };
  }, [
    activeUploadedDocxFile,
    displayFileName,
    importDocxFile,
    setActivePage,
    url,
  ]);
  const updateActivePageFromViewport = React.useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || !pageCount) return;
    const viewportRect = viewport.getBoundingClientRect();
    const viewportCenter = viewportRect.top + viewportRect.height / 2;
    let closestPage = 1;
    let closestDistance = Number.POSITIVE_INFINITY;
    viewport
      .querySelectorAll<HTMLElement>(
        '[data-docx-page-wrapper="true"][data-index]'
      )
      .forEach((page) => {
        const pageIndex = Number(page.dataset.index);
        if (!Number.isFinite(pageIndex)) return;
        const pageRect = page.getBoundingClientRect();
        const pageCenter = pageRect.top + pageRect.height / 2;
        const distance = Math.abs(pageCenter - viewportCenter);
        if (distance < closestDistance) {
          closestDistance = distance;
          closestPage = pageIndex + 1;
        }
      });
    activePageStore.setActivePage((currentPage) =>
      currentPage === closestPage ? currentPage : closestPage
    );
  }, [activePageStore, pageCount]);
  React.useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !pageCount) return;
    let frameId = 0;
    const handleScroll = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(updateActivePageFromViewport);
    };
    frameId = window.requestAnimationFrame(updateActivePageFromViewport);
    viewport.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      window.cancelAnimationFrame(frameId);
      viewport.removeEventListener("scroll", handleScroll);
    };
  }, [pageCount, updateActivePageFromViewport]);
  const scrollToPage = React.useCallback(
    (pageNumber: number) => {
      const viewport = viewportRef.current;
      const targetPageIndex = pageNumber - 1;
      const page = viewport?.querySelector<HTMLElement>(
        `[data-docx-page-wrapper="true"][data-index="${targetPageIndex}"]`
      );
      setActivePage(pageNumber);
      if (!viewport) return;
      if (!page) {
        const pageStridePx =
          (pageLayout.pageHeightPx + pageLayout.viewportDefaults.pageGapPx) *
          (zoomScale / 100);
        viewport.scrollTo({
          top: Math.max(0, targetPageIndex * pageStridePx - 24),
          behavior: "auto",
        });
        return;
      }
      viewport.scrollTo({
        top:
          page.getBoundingClientRect().top -
          viewport.getBoundingClientRect().top +
          viewport.scrollTop -
          24,
        behavior: "auto",
      });
    },
    [
      pageLayout.pageHeightPx,
      pageLayout.viewportDefaults.pageGapPx,
      setActivePage,
      zoomScale,
    ]
  );
  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setZoomScale(resolvedDefaultZoomScale);
    setActivePage(1);
    setReportedPageCount(0);
    setUploadedDocxFile({
      file,
      identity: `${file.name}-${file.size}-${file.lastModified}`,
      sourceUrl: url,
    });
  }
  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-col overflow-hidden bg-oklch(1 0 0) dark:bg-oklch(0.145 0 0)",
        className
      )}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        onChange={handleUpload}
      />
      {showToolbar ? (
        <DocxToolbar
          activePageStore={activePageStore}
          controlsDisabled={controlsDisabled}
          isDark={effectiveIsDark}
          isPreparingDownload={isPreparingDownload}
          onDownload={handleDownload}
          onIsDarkChange={setNightRenderEnabled}
          onPageChange={scrollToPage}
          onShowCommentsChange={setShowComments}
          onShowTrackedChangesChange={setShowTrackedChanges}
          onToggleSidebar={() => setSidebarOpen((open) => !open)}
          onUploadClick={() => fileInputRef.current?.click()}
          pageCount={pageCount}
          setZoomScale={setZoomScale}
          showComments={showComments}
          showDownloadButton={showDownload}
          showNightRenderToggle={shouldRenderNightMode}
          showReviewControls={false}
          showTrackedChanges={showTrackedChanges}
          showUploadButton={showUpload}
          toolbarActions={toolbarActions}
          zoomScale={zoomScale}
        />
      ) : null}
      <div
        ref={viewerShellRef}
        className="relative flex min-h-0 flex-1 overflow-hidden bg-oklch(0.97 0 0)/30 dark:bg-oklch(0.269 0 0)/30"
      >
        <DocumentViewerThumbnailSidebar
          inline={sidebarInline}
          open={thumbnailSidebarVisible}
        >
          <DocxThumbnailSidebarContent
            activePageStore={activePageStore}
            displayFileName={displayFileName}
            editor={editor}
            isLoadingDocument={isLoadingDocument}
            onSelectPage={scrollToPage}
            pageCount={pageCount}
            reportedPageCount={reportedPageCount}
            sidebarOpen={thumbnailSidebarVisible}
          />
        </DocumentViewerThumbnailSidebar>
        <InlineScrollArea2
          className="min-h-0 flex-1"
          style={{ backgroundColor: viewerBackgroundColor }}
          viewportClassName="px-4 py-6"
          viewportProps={{
            "aria-label": "DOCX document",
            onMouseDown: (event) => {
              if (isInteractiveViewerTarget(event.target)) return;
              event.currentTarget.focus({ preventScroll: true });
            },
            tabIndex: 0,
          }}
          viewportRef={setViewportRef}
        >
          {!url && !activeUploadedDocxFile ? (
            <div className="grid h-full min-h-96 place-items-center p-6 text-center">
              <div className="max-w-md rounded-lg border border-oklch(0.922 0 0) bg-oklch(1 0 0) p-4 text-sm shadow-xs dark:border-oklch(1 0 0 / 10%) dark:bg-oklch(0.145 0 0)">
                <div className="font-medium">
                  Upload a Word document to preview
                </div>
                <div className="mt-1 text-oklch(0.556 0 0) dark:text-oklch(0.708 0 0)">
                  Pass a DOCX URL with the <code>src</code> prop or upload a
                  file.
                </div>
                <div className="mt-1 text-oklch(0.556 0 0) dark:text-oklch(0.708 0 0)">
                  Legacy <code>.doc</code> support is limited and experimental;
                  convert to DOCX for best fidelity.
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-4"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <IconPlaceholder
                    lucide="Upload"
                    tabler="IconUpload"
                    hugeicons="Upload01Icon"
                    phosphor="UploadSimpleIcon"
                    remixicon="RiUpload2Line"
                    className="size-4"
                  />
                  Upload Word document
                </Button>
              </div>
            </div>
          ) : loadError ? (
            <div className="grid h-full min-h-96 place-items-center p-6 text-center">
              <div className="max-w-md rounded-lg border border-oklch(0.922 0 0) bg-oklch(1 0 0) p-4 text-sm text-oklch(0.577 0.245 27.325) shadow-xs dark:border-oklch(1 0 0 / 10%) dark:bg-oklch(0.145 0 0) dark:text-oklch(0.704 0.191 22.216)">
                <div className="font-medium">Unable to display DOCX</div>
                <div className="mt-1 text-oklch(0.556 0 0) dark:text-oklch(0.708 0 0)">
                  {loadError}
                </div>
              </div>
            </div>
          ) : isLoadingDocument ? (
            loadingState
          ) : (
            <div className="flex min-h-full w-max min-w-full justify-center">
              <div
                className={cn(
                  "docx-host origin-top",
                  effectiveIsDark && "docx-night-reader-shell"
                )}
                style={{ zoom: zoomScale / 100 }}
              >
                <DocxEditorViewer
                  editor={editor}
                  mode="read-only"
                  showTrackedChanges={showTrackedChanges}
                  renderTrackedChangeCard={renderTrackedChangeCard}
                  showComments={showComments}
                  renderCommentCard={renderCommentCard}
                  loadingState={loadingState}
                  pageBackgroundColor={effectiveIsDark ? "#0a0a0a" : undefined}
                  pageGapBackgroundColor={viewerBackgroundColor}
                  pageVirtualization={pageVirtualization}
                  deferInitialPaginationPaint={false}
                  onPageCountChange={handlePageCountChange}
                />
              </div>
            </div>
          )}
        </InlineScrollArea2>
      </div>
    </div>
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
          "h-full w-full overflow-auto rounded-[inherit] outline-none [&>div]:!block [&>div]:min-h-min focus-visible:ring-2 focus-visible:ring-oklch(0.708 0 0) dark:focus-visible:ring-oklch(0.556 0 0)",
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
function InlineSpinner({ className, ...props }: InlineRegistryIconProps) {
  return (
    <IconPlaceholder
      lucide="LoaderCircle"
      tabler="IconLoader2"
      hugeicons="Loading03Icon"
      phosphor="CircleNotchIcon"
      remixicon="RiLoader4Line"
      role="status"
      aria-label="Loading"
      className={cn("size-4 animate-spin", className)}
      {...props}
    />
  );
}
type InlineRegistryIconProps = Omit<
  React.ComponentProps<"svg">,
  "children" | "strokeWidth"
> & { strokeWidth?: number };
