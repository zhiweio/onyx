"use client";

import { useState } from "react";
import {
  InputSelect,
  InputTags,
  InputTextArea,
  InputTypeIn,
} from "@opal/components";
import { InputVertical } from "@opal/layouts";
import {
  CATALOG_DESCRIPTION_MAX,
  CATALOG_TAG_MAX,
  CATALOG_TAGS_MAX_COUNT,
  canAcceptCatalogTag,
  normalizeCatalogTag,
} from "@/lib/system-catalog/limits";
import {
  SYSTEM_CATALOG_CATEGORIES,
  type SystemCatalogCategory,
} from "@/lib/system-catalog/types";

export interface CatalogListingFieldCopy {
  name: string;
  namePlaceholder: string;
  description: string;
  descriptionPlaceholder: string;
  category: string;
  tags: string;
  tagsPlaceholder: string;
  tagsHint: string;
  count: (used: number, max: number) => string;
  categoryLabel: (category: SystemCatalogCategory) => string;
}

interface CatalogListingFieldsProps {
  name: string;
  description: string;
  category: SystemCatalogCategory;
  tags: string[];
  nameMax: number;
  disabled?: boolean;
  copy: CatalogListingFieldCopy;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onCategoryChange: (value: SystemCatalogCategory) => void;
  onTagsChange: (tags: string[]) => void;
}

export default function CatalogListingFields({
  name,
  description,
  category,
  tags,
  nameMax,
  disabled = false,
  copy,
  onNameChange,
  onDescriptionChange,
  onCategoryChange,
  onTagsChange,
}: CatalogListingFieldsProps) {
  const [tagDraft, setTagDraft] = useState("");
  const variant = disabled ? "disabled" : "primary";

  function addTag(raw: string) {
    const tag = normalizeCatalogTag(raw);
    if (!canAcceptCatalogTag(tag, tags)) {
      setTagDraft("");
      return;
    }
    onTagsChange([...tags, tag]);
    setTagDraft("");
  }

  function handleTagDraftChange(value: string) {
    if (value.includes(",")) {
      const parts = value.split(",");
      const remainder = parts.pop() ?? "";
      let next = tags;
      for (const part of parts) {
        const tag = normalizeCatalogTag(part);
        if (canAcceptCatalogTag(tag, next)) {
          next = [...next, tag];
        }
      }
      if (next !== tags) onTagsChange(next);
      setTagDraft(remainder);
      return;
    }
    setTagDraft(value.slice(0, CATALOG_TAG_MAX));
  }

  return (
    <div className="flex w-full min-w-0 flex-col gap-3">
      <InputVertical
        withLabel="catalog-listing-name"
        title={copy.name}
        topRight={copy.count(name.length, nameMax)}
      >
        <InputTypeIn
          id="catalog-listing-name"
          value={name}
          maxLength={nameMax}
          placeholder={copy.namePlaceholder}
          variant={variant}
          onChange={(event) => onNameChange(event.target.value)}
        />
      </InputVertical>
      <InputVertical
        withLabel="catalog-listing-description"
        title={copy.description}
        topRight={copy.count(description.length, CATALOG_DESCRIPTION_MAX)}
      >
        <InputTextArea
          id="catalog-listing-description"
          rows={3}
          maxRows={8}
          autoResize
          value={description}
          maxLength={CATALOG_DESCRIPTION_MAX}
          placeholder={copy.descriptionPlaceholder}
          variant={variant}
          onChange={(event) => onDescriptionChange(event.target.value)}
        />
      </InputVertical>
      <InputVertical title={copy.category}>
        <InputSelect
          value={category}
          disabled={disabled}
          onValueChange={(value) =>
            onCategoryChange(value as SystemCatalogCategory)
          }
        >
          <InputSelect.Trigger placeholder={copy.category}>
            {copy.categoryLabel(category)}
          </InputSelect.Trigger>
          <InputSelect.Content>
            {SYSTEM_CATALOG_CATEGORIES.map((value) => (
              <InputSelect.Item key={value} value={value}>
                {copy.categoryLabel(value)}
              </InputSelect.Item>
            ))}
          </InputSelect.Content>
        </InputSelect>
      </InputVertical>
      <InputVertical
        title={copy.tags}
        description={copy.tagsHint}
        topRight={copy.count(tags.length, CATALOG_TAGS_MAX_COUNT)}
      >
        <InputTags
          tags={tags.map((tag) => ({ id: tag, label: tag }))}
          onRemoveTag={(id) =>
            onTagsChange(tags.filter((tag) => tag !== id))
          }
          onAdd={addTag}
          value={tagDraft}
          onChange={handleTagDraftChange}
          placeholder={copy.tagsPlaceholder}
          disabled={disabled}
          minRows={2}
        />
      </InputVertical>
    </div>
  );
}
