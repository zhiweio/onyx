"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Card,
  CompactMarkdown,
  InputTextArea,
  InputTypeIn,
  MessageCard,
  Modal,
  Tag,
  Text,
} from "@opal/components";
import { InputVertical } from "@opal/layouts";
import { SvgEdit, SvgSimpleLoader } from "@opal/icons";
import type { CatalogPatchInput } from "@/lib/system-catalog/api";
import { useCatalogItem } from "@/lib/system-catalog/hooks";
import {
  CATALOG_BODY_MAX,
  CATALOG_NAME_MAX,
  CATALOG_SKILL_NAME_MAX,
} from "@/lib/system-catalog/limits";
import {
  categoryMessageKey,
  categoryTagColor,
  isSystemSkillItem,
  publishStatusMessageKey,
  publishStatusTagColor,
  type CatalogItem,
  type GalleryKind,
  type SystemCatalogCategory,
  type SystemReportTemplateItem,
  type SystemSkillItem,
} from "@/lib/system-catalog/types";
import CatalogListingFields from "@/sections/catalog/CatalogListingFields";

interface EditCatalogModalProps {
  kind: GalleryKind;
  item: CatalogItem;
  pending: boolean;
  onClose: () => void;
  onSave: (input: CatalogPatchInput) => Promise<void>;
}

function isTemplateItem(
  item: CatalogItem,
  kind: GalleryKind
): item is SystemReportTemplateItem {
  return kind === "report-templates";
}

export default function EditCatalogModal({
  kind,
  item,
  pending,
  onClose,
  onSave,
}: EditCatalogModalProps) {
  const t = useTranslations("admin.craftCatalog");
  const tGallery = useTranslations("craft.gallery");
  const [name, setName] = useState(item.name);
  const [description, setDescription] = useState(item.description);
  const [category, setCategory] = useState<SystemCatalogCategory>(
    item.category
  );
  const [tags, setTags] = useState<string[]>(item.tags);
  const [body, setBody] = useState("");

  const { data: skillDetail, isLoading: skillDetailLoading } =
    useCatalogItem<SystemSkillItem>(
      "skills",
      kind === "skills" ? item.id : undefined
    );

  useEffect(() => {
    setName(item.name);
    setDescription(item.description);
    setCategory(item.category);
    setTags(item.tags);
    if (isTemplateItem(item, kind)) {
      setBody(item.body);
    }
  }, [item, kind]);

  const nameMax =
    kind === "skills" ? CATALOG_SKILL_NAME_MAX : CATALOG_NAME_MAX;
  const canSave =
    !pending &&
    name.trim().length > 0 &&
    description.trim().length > 0 &&
    (kind !== "report-templates" || body.trim().length > 0);

  const listingCopy = useMemo(
    () => ({
      name: t("edit.fields.name.label"),
      namePlaceholder: t("edit.fields.name.placeholder"),
      description: t("edit.fields.description.label"),
      descriptionPlaceholder: t("edit.fields.description.placeholder"),
      category: t("edit.fields.category.label"),
      tags: t("edit.fields.tags.label"),
      tagsPlaceholder: t("edit.fields.tags.placeholder"),
      tagsHint: t("edit.fields.tags.hint"),
      count: (used: number, max: number) =>
        t("edit.count.label", { used, max }),
      categoryLabel: (value: SystemCatalogCategory) =>
        tGallery(categoryMessageKey(value)),
    }),
    [t, tGallery]
  );

  const skillItem = isSystemSkillItem(item) ? item : skillDetail;
  const instructions = skillDetail?.instructions_markdown ?? null;

  async function handleSave() {
    const input: CatalogPatchInput = {
      name: name.trim(),
      description: description.trim(),
      category,
      tags,
    };
    if (kind === "report-templates") {
      input.body = body;
    }
    await onSave(input);
  }

  return (
    <Modal open onOpenChange={(open) => !open && !pending && onClose()}>
      <Modal.Content width="lg" height="lg">
        <Modal.Header
          icon={SvgEdit}
          title={t("edit.title", { name: item.name })}
          description={t("edit.description")}
          onClose={pending ? undefined : onClose}
        />
        <Modal.Body alignItems="stretch" gap={3}>
          <div className="flex w-full min-w-0 flex-col gap-3">
            <div className="flex w-full min-w-0 flex-wrap items-center gap-1">
              <Tag
                size="sm"
                color={publishStatusTagColor(item.publish_status)}
                title={t(publishStatusMessageKey(item.publish_status))}
              />
              <Tag
                size="sm"
                color={categoryTagColor(item.category)}
                title={tGallery(categoryMessageKey(item.category))}
              />
              <Tag
                size="sm"
                color="gray"
                title={tGallery("card.version.label", {
                  version: item.version,
                })}
              />
            </div>
            <InputVertical
              withLabel="catalog-listing-slug"
              title={t("edit.fields.slug.label")}
              description={t("edit.fields.slug.description")}
            >
              <InputTypeIn
                id="catalog-listing-slug"
                value={item.slug}
                variant="readOnly"
              />
            </InputVertical>
            {skillItem?.is_built_in_content && (
              <MessageCard
                variant="info"
                title={t("edit.builtinNote.title")}
                description={t("edit.builtinNote.description")}
              />
            )}
            <CatalogListingFields
              name={name}
              description={description}
              category={category}
              tags={tags}
              nameMax={nameMax}
              disabled={pending}
              copy={listingCopy}
              onNameChange={setName}
              onDescriptionChange={setDescription}
              onCategoryChange={setCategory}
              onTagsChange={setTags}
            />
            {kind === "skills" && (
              <div className="flex w-full min-w-0 flex-col gap-1.5">
                <Text font="main-ui-action">{t("edit.preview.title")}</Text>
                <Card border="solid" rounding={2} padding={3}>
                  <div className="max-h-72 min-w-0 overflow-y-auto break-words">
                    {skillDetailLoading ? (
                      <SvgSimpleLoader />
                    ) : instructions ? (
                      <CompactMarkdown>{instructions}</CompactMarkdown>
                    ) : (
                      <Text font="secondary-body" color="text-03">
                        {t("edit.preview.empty")}
                      </Text>
                    )}
                  </div>
                </Card>
              </div>
            )}
            {kind === "report-templates" && (
              <InputVertical
                withLabel="catalog-listing-body"
                title={t("edit.fields.body.label")}
                topRight={t("edit.count.label", {
                  used: body.length,
                  max: CATALOG_BODY_MAX,
                })}
              >
                <InputTextArea
                  id="catalog-listing-body"
                  rows={8}
                  maxRows={16}
                  autoResize
                  value={body}
                  maxLength={CATALOG_BODY_MAX}
                  variant={pending ? "disabled" : "primary"}
                  onChange={(event) => setBody(event.target.value)}
                />
              </InputVertical>
            )}
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button prominence="secondary" disabled={pending} onClick={onClose}>
            {t("edit.cancel.label")}
          </Button>
          <Button disabled={!canSave} onClick={() => void handleSave()}>
            {t("edit.confirm.label")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
