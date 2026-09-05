"use client";

import { useTranslations } from "next-intl";
import {
  Button,
  CompactMarkdown,
  MessageCard,
  Modal,
  Tag,
  Text,
} from "@opal/components";
import { SvgBlocks, SvgDownload, SvgSimpleLoader } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import { useGalleryItem } from "@/lib/system-catalog/hooks";
import { galleryReportTemplateDocxUrl } from "@/lib/system-catalog/api";
import { placeholderToken } from "@/lib/report-templates/types";
import {
  categoryMessageKey,
  categoryTagColor,
  isDocxCatalogTemplate,
  type AnyCatalogItem,
  type GalleryKind,
  type SystemReportTemplateItem,
  type SystemScenarioItem,
  type SystemSkillItem,
} from "@/lib/system-catalog/types";

interface GalleryPreviewModalProps {
  kind: GalleryKind;
  entryId: string;
  fallbackTitle?: string;
  onClose: () => void;
  onFork?: (entryId: string) => void;
  forking?: boolean;
}

/** The readable body differs per kind; listing endpoints omit it entirely. */
function previewBody(kind: GalleryKind, item: AnyCatalogItem): string | null {
  if (kind === "skills") {
    return (item as SystemSkillItem).instructions_markdown;
  }
  if (kind === "report-templates") {
    return (item as SystemReportTemplateItem).body;
  }
  return null;
}

function scenarioSkills(item: AnyCatalogItem): string[] {
  return (item as SystemScenarioItem).skill_slugs ?? [];
}

export default function GalleryPreviewModal({
  kind,
  entryId,
  fallbackTitle,
  onClose,
  onFork,
  forking = false,
}: GalleryPreviewModalProps) {
  const t = useTranslations("craft.gallery");
  const { data, error, isLoading } = useGalleryItem<AnyCatalogItem>(
    kind,
    entryId,
  );

  const body = data ? previewBody(kind, data) : null;
  const skills = data && kind === "scenarios" ? scenarioSkills(data) : [];
  const wordTemplate =
    data && kind === "report-templates" && isDocxCatalogTemplate(data)
      ? data
      : null;

  return (
    <Modal open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <Modal.Content width="lg" height="lg">
        <Modal.Header
          icon={SvgBlocks}
          title={data?.name ?? fallbackTitle ?? t("preview.fallbackTitle")}
          description={data?.description}
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

          {data && !isLoading && !error && (
            <Section gap={4} alignItems="stretch">
              <div className="flex flex-row flex-wrap items-center gap-1">
                <Tag
                  size="sm"
                  color={categoryTagColor(data.category)}
                  title={t(categoryMessageKey(data.category))}
                />
                {data.tags.map((tag) => (
                  <Tag key={tag} size="sm" color="gray" title={tag} />
                ))}
                {wordTemplate && (
                  <span data-testid="GalleryPreview/word">
                    <Tag
                      size="sm"
                      color="green"
                      title={t("card.kind.word.label")}
                    />
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div className="flex flex-col gap-1">
                  <Text font="main-ui-action" color="text-05">
                    {t("preview.identifier.label")}
                  </Text>
                  <Text font="main-ui-body" color="text-04">
                    {data.slug}
                  </Text>
                </div>
                <div className="flex flex-col gap-1">
                  <Text font="main-ui-action" color="text-05">
                    {t("preview.version.label")}
                  </Text>
                  <Text font="main-ui-body" color="text-04">
                    {t("card.version.label", { version: data.version })}
                  </Text>
                </div>
              </div>

              {data.changelog && (
                <div className="flex flex-col gap-1">
                  <Text font="main-ui-action" color="text-05">
                    {t("preview.changelog.label")}
                  </Text>
                  <Text font="main-ui-body" color="text-04">
                    {data.changelog}
                  </Text>
                </div>
              )}

              {skills.length > 0 && (
                <div className="flex flex-col gap-1">
                  <Text font="main-ui-action" color="text-05">
                    {t("preview.skills.label")}
                  </Text>
                  <div className="flex flex-row flex-wrap gap-1">
                    {skills.map((slug) => (
                      <Tag key={slug} size="sm" color="blue" title={slug} />
                    ))}
                  </div>
                </div>
              )}

              {wordTemplate && (
                <Section gap={1} alignItems="stretch">
                  <Text font="main-ui-action" color="text-05">
                    {t("preview.placeholders.label")}
                  </Text>
                  <Text font="main-ui-body" color="text-04">
                    {t("preview.wordRequired.description")}
                  </Text>
                  {wordTemplate.placeholders.length > 0 && (
                    <div
                      className="flex flex-row flex-wrap gap-1"
                      data-testid="GalleryPreview/placeholders"
                    >
                      {wordTemplate.placeholders.map((placeholder) => (
                        <Tag
                          key={placeholder.name}
                          size="sm"
                          color="blue"
                          title={placeholderToken(placeholder)}
                        />
                      ))}
                    </div>
                  )}
                  <Button
                    prominence="secondary"
                    icon={SvgDownload}
                    href={galleryReportTemplateDocxUrl(wordTemplate.id)}
                    data-testid="GalleryPreview/download"
                  >
                    {t("preview.downloadWord.label")}
                  </Button>
                </Section>
              )}

              {body && (
                <Section gap={1} alignItems="stretch">
                  <Text font="main-ui-action" color="text-05">
                    {t("preview.content.label")}
                  </Text>
                  <div className="rounded-lg border border-border p-3 overflow-y-auto overflow-x-hidden bg-background-neutral-00 max-h-[40dvh]">
                    <CompactMarkdown>{body}</CompactMarkdown>
                  </div>
                </Section>
              )}
            </Section>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button prominence="secondary" onClick={onClose}>
            {t("preview.closeButton.label")}
          </Button>
          {onFork && (
            <Button
              disabled={forking || isLoading}
              onClick={() => onFork(entryId)}
            >
              {t("card.fork.tooltip")}
            </Button>
          )}
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
