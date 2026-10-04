"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import useSWR from "swr";
import { Button, CompactMarkdown, MessageCard, Text } from "@opal/components";
import {
  SvgBlocks,
  SvgDownload,
  SvgSimpleLoader,
  SvgUploadCloud,
} from "@opal/icons";
import { Modal } from "@opal/components";
import { toast } from "@opal/layouts";
import { Section } from "@/layouts/general-layouts";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";
import { downloadSkillBundle, replaceUserSkillBundle } from "@/lib/skills/api";
import type { SkillDetail } from "@/lib/skills/types";
import SkillFileTree from "@/sections/skills/SkillFileTree";
import InstructionsDisplayModeToggle, {
  type InstructionsDisplayMode,
} from "@/sections/skills/InstructionsDisplayModeToggle";

interface SkillPreviewModalProps {
  open: boolean;
  skillId: string | null;
  fallbackTitle?: string;
  unavailableReason?: string | null;
  onClose: () => void;
  /** Called after the skill's bundle is replaced so lists can refresh. */
  onUpdated?: () => void;
}

// Message keys under `skills.modals`, not copy — the literal union keeps `t()`
// statically checked while this stays a plain helper.
type MetadataLabelKey =
  | "preview.metadata.createdBy.label"
  | "preview.metadata.createdAt.label"
  | "preview.metadata.updatedAt.label"
  | "preview.metadata.status.label"
  | "preview.metadata.visibility.label"
  | "preview.metadata.externalApp.label";

interface MetadataRow {
  labelKey: MetadataLabelKey;
  value: string;
}

function formatTimestamp(value: string | null, locale: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function metadataRows(
  detail: SkillDetail,
  locale: string,
  t: ReturnType<typeof useTranslations>
): MetadataRow[] {
  const rows: MetadataRow[] = [];
  if (detail.source === "builtin") {
    rows.push({
      labelKey: "preview.metadata.createdBy.label",
      value: "Onyx",
    });
  } else {
    if (detail.author_email) {
      rows.push({
        labelKey: "preview.metadata.createdBy.label",
        value: detail.author_email,
      });
    }
    const createdAt = formatTimestamp(detail.created_at, locale);
    if (createdAt) {
      rows.push({
        labelKey: "preview.metadata.createdAt.label",
        value: createdAt,
      });
    }
    const updatedAt = formatTimestamp(detail.updated_at, locale);
    if (updatedAt) {
      rows.push({
        labelKey: "preview.metadata.updatedAt.label",
        value: updatedAt,
      });
    }
    rows.push({
      labelKey: "preview.metadata.status.label",
      value:
        detail.is_valid === false
          ? t("preview.status.invalid")
          : t("preview.status.valid"),
    });
    rows.push({
      labelKey: "preview.metadata.visibility.label",
      value:
        detail.public_permission !== null
          ? t("preview.visibility.organization")
          : detail.user_shares.length > 0 || detail.group_shares.length > 0
            ? t("preview.visibility.shared")
            : t("preview.visibility.personal"),
    });
  }
  if (detail.external_app) {
    rows.push({
      labelKey: "preview.metadata.externalApp.label",
      value: detail.external_app.name,
    });
  }
  return rows;
}

export default function SkillPreviewModal({
  open,
  skillId,
  fallbackTitle,
  unavailableReason = null,
  onClose,
  onUpdated,
}: SkillPreviewModalProps) {
  const t = useTranslations("skills.modals");
  const locale = useLocale();
  const [instructionsDisplayMode, setInstructionsDisplayMode] =
    useState<InstructionsDisplayMode>("rendered");
  const [downloading, setDownloading] = useState(false);
  const [uploadingBundle, setUploadingBundle] = useState(false);
  const bundleInputRef = useRef<HTMLInputElement>(null);
  const swrKey = open && skillId ? SWR_KEYS.userSkillDetail(skillId) : null;
  const {
    data: detail,
    error,
    isLoading,
    mutate,
  } = useSWR<SkillDetail>(swrKey, errorHandlingFetcher);
  const instructionsMarkdown =
    detail?.instructions_markdown || t("preview.noInstructions.message");
  const dependency = detail?.external_app;
  const dependencyUnavailableReason =
    dependency && !dependency.ready
      ? dependency.enabled
        ? t("preview.unavailable.appNotConnected", { appName: dependency.name })
        : t("preview.unavailable.appDisabled", { appName: dependency.name })
      : null;
  const displayedUnavailableReason =
    unavailableReason ?? dependencyUnavailableReason;
  const canReplaceBundle =
    detail?.source === "custom" &&
    (detail.user_permission === "OWNER" || detail.user_permission === "EDITOR");

  useEffect(() => {
    if (open) {
      setInstructionsDisplayMode("rendered");
    }
  }, [open, skillId]);

  async function handleDownload() {
    if (!detail) return;
    setDownloading(true);
    try {
      await downloadSkillBundle(detail);
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("preview.toasts.downloadFailed")
      );
    } finally {
      setDownloading(false);
    }
  }

  async function handleBundleSelected(file: File) {
    if (!detail) return;
    setUploadingBundle(true);
    try {
      await replaceUserSkillBundle(detail.id, file);
      toast.success(t("preview.toasts.bundleReplaced", { name: detail.name }));
      await mutate();
      onUpdated?.();
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("preview.toasts.bundleReplaceFailed")
      );
    } finally {
      setUploadingBundle(false);
    }
  }

  return (
    <Modal open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <Modal.Content width="lg" height="lg">
        <Modal.Header
          icon={SvgBlocks}
          title={detail?.name ?? fallbackTitle ?? t("preview.fallbackTitle")}
          description={detail?.description}
          onClose={onClose}
        />
        <Modal.Body>
          {isLoading && (
            <div className="flex items-center justify-center min-h-40">
              <SvgSimpleLoader />
            </div>
          )}

          {error && !isLoading && (
            <MessageCard
              variant="error"
              title={t("preview.loadError.title")}
              description={t("preview.loadError.description")}
            />
          )}

          {detail && !isLoading && !error && (
            <Section gap={4} alignItems="stretch">
              {displayedUnavailableReason && (
                <MessageCard
                  variant="warning"
                  title={t("preview.unavailable.title")}
                  description={displayedUnavailableReason}
                />
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {metadataRows(detail, locale, t).map((row) => (
                  <div key={row.labelKey} className="flex flex-col gap-1">
                    <Text font="main-ui-action" color="text-05">
                      {t(row.labelKey)}
                    </Text>
                    <Text font="main-ui-body" color="text-04">
                      {row.value}
                    </Text>
                  </div>
                ))}
              </div>

              <Section gap={1} alignItems="stretch">
                <div className="flex items-center justify-between gap-2">
                  <Text font="main-ui-action" color="text-05">
                    {t("preview.instructions.title")}
                  </Text>
                  <InstructionsDisplayModeToggle
                    value={instructionsDisplayMode}
                    onChange={setInstructionsDisplayMode}
                  />
                </div>
                <div className="rounded-lg border border-border p-3 overflow-y-auto overflow-x-hidden bg-background-neutral-00 max-h-[36dvh]">
                  {instructionsDisplayMode === "rendered" ? (
                    <CompactMarkdown>{instructionsMarkdown}</CompactMarkdown>
                  ) : (
                    <pre className="m-0 whitespace-pre-wrap wrap-break-word font-mono text-xs leading-5 text-text-04">
                      {instructionsMarkdown}
                    </pre>
                  )}
                </div>
              </Section>

              <Section gap={1} alignItems="stretch">
                <Text font="main-ui-action" color="text-05">
                  {t("preview.files.title")}
                </Text>
                <div className="rounded-lg border border-border p-3 overflow-y-auto bg-background-neutral-00 max-h-[24dvh]">
                  <SkillFileTree
                    files={detail.files}
                    emptyMessage={t("preview.files.empty")}
                  />
                </div>
              </Section>
            </Section>
          )}
        </Modal.Body>
        <Modal.Footer>
          <div className="flex w-full items-center justify-between gap-2">
            {canReplaceBundle ? (
              <Button
                prominence="secondary"
                onClick={() => bundleInputRef.current?.click()}
                disabled={uploadingBundle}
                icon={SvgUploadCloud}
              >
                {uploadingBundle
                  ? t("preview.uploadVersion.pendingLabel")
                  : t("preview.uploadVersion.label")}
              </Button>
            ) : (
              <span />
            )}
            <div className="flex items-center gap-2">
              <Button
                prominence="secondary"
                icon={SvgDownload}
                disabled={!detail || downloading}
                onClick={() => void handleDownload()}
              >
                {t("preview.downloadButton.label")}
              </Button>
              <Button onClick={onClose}>
                {t("preview.closeButton.label")}
              </Button>
            </div>
          </div>
        </Modal.Footer>
        <input
          ref={bundleInputRef}
          type="file"
          accept=".zip,.md"
          className="hidden"
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void handleBundleSelected(file);
          }}
        />
      </Modal.Content>
    </Modal>
  );
}
