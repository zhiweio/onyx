"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, InputTextArea, InputTypeIn, Modal } from "@opal/components";
import { InputVertical } from "@opal/layouts";
import { SvgEdit } from "@opal/icons";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import type { CatalogPatchInput } from "@/lib/system-catalog/api";
import {
  SYSTEM_CATALOG_CATEGORIES,
  categoryMessageKey,
  type CatalogItem,
  type GalleryKind,
  type SystemCatalogCategory,
  type SystemReportTemplateItem,
} from "@/lib/system-catalog/types";

interface EditCatalogModalProps {
  kind: GalleryKind;
  item: CatalogItem;
  pending: boolean;
  onClose: () => void;
  onSave: (input: CatalogPatchInput) => Promise<void>;
}

function isTemplateItem(
  item: CatalogItem,
  kind: GalleryKind,
): item is SystemReportTemplateItem {
  return kind === "report-templates";
}

function joinList(values: string[]): string {
  return values.join(", ");
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
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
    item.category,
  );
  const [tagsText, setTagsText] = useState(joinList(item.tags));
  const [body, setBody] = useState("");

  useEffect(() => {
    setName(item.name);
    setDescription(item.description);
    setCategory(item.category);
    setTagsText(joinList(item.tags));
    if (isTemplateItem(item, kind)) {
      setBody(item.body);
    }
  }, [item, kind]);

  async function handleSave() {
    const input: CatalogPatchInput = {
      name: name.trim(),
      description: description.trim(),
      category,
      tags: splitList(tagsText),
    };

    if (kind === "report-templates") {
      input.body = body;
    }

    await onSave(input);
  }

  return (
    <Modal open onOpenChange={(open) => !open && !pending && onClose()}>
      <Modal.Content width="md" height="fit">
        <Modal.Header
          icon={SvgEdit}
          title={t("edit.title", { name: item.name })}
          description={t("edit.description")}
          onClose={pending ? undefined : onClose}
        />
        <Modal.Body>
          <div className="flex flex-col gap-3">
            <InputVertical withLabel title={t("edit.fields.name.label")}>
              <InputTypeIn
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </InputVertical>
            <InputVertical withLabel title={t("edit.fields.description.label")}>
              <InputTextArea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </InputVertical>
            <InputVertical withLabel title={t("edit.fields.category.label")}>
              <InputSelect
                value={category}
                onValueChange={(value) =>
                  setCategory(value as SystemCatalogCategory)
                }
              >
                <InputSelect.Trigger
                  placeholder={t("edit.fields.category.label")}
                />
                <InputSelect.Content>
                  {SYSTEM_CATALOG_CATEGORIES.map((value) => (
                    <InputSelect.Item key={value} value={value}>
                      {tGallery(categoryMessageKey(value))}
                    </InputSelect.Item>
                  ))}
                </InputSelect.Content>
              </InputSelect>
            </InputVertical>
            <InputVertical withLabel title={t("edit.fields.tags.label")}>
              <InputTypeIn
                value={tagsText}
                placeholder={t("edit.fields.tags.placeholder")}
                onChange={(event) => setTagsText(event.target.value)}
              />
            </InputVertical>
            {kind === "report-templates" && (
              <InputVertical withLabel title={t("edit.fields.body.label")}>
                <InputTextArea
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                />
              </InputVertical>
            )}
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button
            prominence="secondary"
            disabled={pending}
            onClick={onClose}
          >
            {t("edit.cancel.label")}
          </Button>
          <Button
            disabled={pending || name.trim().length === 0}
            onClick={() => void handleSave()}
          >
            {t("edit.confirm.label")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
