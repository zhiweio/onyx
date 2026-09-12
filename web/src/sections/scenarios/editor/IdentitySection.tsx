"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  InputSelect,
  InputTextArea,
  InputTypeIn,
  SelectCard,
  Tag,
  Text,
} from "@opal/components";
import { Content, InputVertical } from "@opal/layouts";
import { SvgPlus, SvgTrash } from "@opal/icons";
import { cn } from "@opal/utils";
import {
  BUILTIN_SCENARIO_DOMAINS,
  isBuiltinScenarioDomain,
  isUncategorizedDomain,
  normalizeScenarioDomain,
  scenarioDomainMessageKey,
} from "@/lib/scenarios/types";
import {
  SYSTEM_CATALOG_CATEGORIES,
  categoryMessageKey,
  type SystemCatalogCategory,
} from "@/lib/system-catalog/types";
import EditorSection from "@/sections/scenarios/editor/EditorSection";
import type {
  ScenarioDraft,
  ScenarioEditorMode,
} from "@/sections/scenarios/editor/types";

const DOMAIN_NAME_MAX = 64;

interface IdentitySectionProps {
  mode: ScenarioEditorMode;
  isCreating: boolean;
  fieldsLocked: boolean;
  draft: ScenarioDraft;
  knownCustomDomains: string[];
  onDraftChange: (patch: Partial<ScenarioDraft>) => void;
}

export default function IdentitySection({
  mode,
  isCreating,
  fieldsLocked,
  draft,
  knownCustomDomains,
  onDraftChange,
}: IdentitySectionProps) {
  const t = useTranslations("craft.scenarioEditor");
  const tScenarios = useTranslations("craft.scenarios");
  const tGallery = useTranslations("craft.gallery");
  const [domainQuery, setDomainQuery] = useState("");
  const [tagDraft, setTagDraft] = useState("");
  const [createdDomains, setCreatedDomains] = useState<string[]>([]);

  const customDomains = useMemo(() => {
    const names = new Set(knownCustomDomains);
    for (const extra of createdDomains) {
      names.add(extra);
    }
    if (
      !isBuiltinScenarioDomain(draft.domain) &&
      !isUncategorizedDomain(draft.domain)
    ) {
      names.add(draft.domain);
    }
    return Array.from(names).sort((left, right) => left.localeCompare(right));
  }, [createdDomains, draft.domain, knownCustomDomains]);

  const visibleCustomDomains = useMemo(() => {
    const query = domainQuery.trim().toLowerCase();
    if (!query) return customDomains;
    return customDomains.filter((item) => item.toLowerCase().includes(query));
  }, [customDomains, domainQuery]);

  const domainCreateName = domainQuery.trim().slice(0, DOMAIN_NAME_MAX);
  const canCreateDomain =
    domainCreateName.length > 0 &&
    !isBuiltinScenarioDomain(domainCreateName) &&
    !isUncategorizedDomain(domainCreateName) &&
    !customDomains.some(
      (item) => item.toLowerCase() === domainCreateName.toLowerCase()
    );

  const selectedCustomDomain =
    !isBuiltinScenarioDomain(draft.domain) &&
    !isUncategorizedDomain(draft.domain)
      ? draft.domain
      : undefined;

  const customCardSelected =
    isUncategorizedDomain(draft.domain) ||
    !isBuiltinScenarioDomain(draft.domain);

  function selectDomain(next: string) {
    const normalized = normalizeScenarioDomain(next);
    if (
      !isBuiltinScenarioDomain(normalized) &&
      !isUncategorizedDomain(normalized)
    ) {
      setCreatedDomains((current) =>
        current.includes(normalized) ? current : [...current, normalized]
      );
    }
    onDraftChange({ domain: normalized });
    setDomainQuery("");
  }

  function addTag(raw: string) {
    const tag = raw.trim().toLowerCase();
    if (!tag || draft.tags.includes(tag)) return;
    onDraftChange({ tags: [...draft.tags, tag] });
    setTagDraft("");
  }

  return (
    <EditorSection
      title={t("sections.identity.title")}
      description={t("sections.identity.description")}
    >
      <InputVertical withLabel="scenario-name" title={t("identity.name.title")}>
        <InputTypeIn
          id="scenario-name"
          value={draft.name}
          maxLength={128}
          placeholder={t("identity.name.placeholder")}
          variant={fieldsLocked ? "disabled" : "primary"}
          onChange={(event) => onDraftChange({ name: event.target.value })}
        />
      </InputVertical>

      {mode === "catalog" && (
        <InputVertical withLabel="scenario-slug" title={t("identity.slug.title")}>
          <InputTypeIn
            id="scenario-slug"
            value={draft.slug}
            maxLength={64}
            placeholder={t("identity.slug.placeholder")}
            variant={fieldsLocked || !isCreating ? "disabled" : "primary"}
            onChange={(event) => onDraftChange({ slug: event.target.value })}
          />
        </InputVertical>
      )}

      <InputVertical
        withLabel="scenario-description"
        title={t("identity.description.title")}
      >
        <InputTextArea
          id="scenario-description"
          rows={3}
          value={draft.description}
          placeholder={t("identity.description.placeholder")}
          autoResize
          maxRows={6}
          variant={fieldsLocked ? "disabled" : "primary"}
          onChange={(event) =>
            onDraftChange({ description: event.target.value })
          }
        />
      </InputVertical>

      {mode === "user" ? (
        <InputVertical title={t("identity.domain.title")}>
          <div className="flex flex-col gap-2">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {BUILTIN_SCENARIO_DOMAINS.map((item) => (
                <SelectCard
                  key={item}
                  state={draft.domain === item ? "selected" : "empty"}
                  padding={2}
                  rounding={3}
                  onClick={
                    fieldsLocked ? undefined : () => selectDomain(item)
                  }
                >
                  <Content
                    sizePreset="main-ui"
                    variant="section"
                    title={tScenarios(scenarioDomainMessageKey(item))}
                    description={
                      item === "tax"
                        ? t("identity.domain.tax.description")
                        : t("identity.domain.biomed.description")
                    }
                  />
                </SelectCard>
              ))}
              <SelectCard
                state={customCardSelected ? "selected" : "empty"}
                padding={2}
                rounding={3}
                onClick={
                  fieldsLocked
                    ? undefined
                    : () => selectDomain("custom")
                }
              >
                <Content
                  sizePreset="main-ui"
                  variant="section"
                  title={tScenarios(scenarioDomainMessageKey("custom"))}
                  description={t("identity.domain.custom.description")}
                />
              </SelectCard>
            </div>
            {customCardSelected && (
              <InputSelect
                value={selectedCustomDomain}
                disabled={fieldsLocked}
                onValueChange={selectDomain}
                onOpenChange={(open) => {
                  if (open) setDomainQuery("");
                }}
              >
                <InputSelect.Trigger
                  placeholder={t("identity.domain.placeholder")}
                />
                <InputSelect.Content>
                  <InputSelect.Search
                    value={domainQuery}
                    onChange={(event) =>
                      setDomainQuery(
                        event.target.value.slice(0, DOMAIN_NAME_MAX)
                      )
                    }
                    placeholder={t("identity.domain.search.placeholder")}
                  />
                  {visibleCustomDomains.map((item) => (
                    <InputSelect.Item key={item} value={item}>
                      {item}
                    </InputSelect.Item>
                  ))}
                  {canCreateDomain ? (
                    <InputSelect.Item value={domainCreateName}>
                      {t("identity.domain.create.label", {
                        name: domainCreateName,
                      })}
                    </InputSelect.Item>
                  ) : null}
                  {visibleCustomDomains.length === 0 && !canCreateDomain ? (
                    <div className="px-2 py-1.5">
                      <Text color="text-03">
                        {t("identity.domain.empty.text")}
                      </Text>
                    </div>
                  ) : null}
                </InputSelect.Content>
              </InputSelect>
            )}
          </div>
        </InputVertical>
      ) : (
        <div className="flex flex-col gap-3">
          <InputVertical title={t("identity.category.title")}>
            <InputSelect
              value={draft.category}
              disabled={fieldsLocked}
              onValueChange={(value) =>
                onDraftChange({
                  category: value as SystemCatalogCategory,
                })
              }
            >
              <InputSelect.Trigger placeholder={t("identity.category.title")} />
              <InputSelect.Content>
                {SYSTEM_CATALOG_CATEGORIES.map((value) => (
                  <InputSelect.Item key={value} value={value}>
                    {tGallery(categoryMessageKey(value))}
                  </InputSelect.Item>
                ))}
              </InputSelect.Content>
            </InputSelect>
          </InputVertical>
          <InputVertical title={t("identity.tags.title")}>
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-1">
                {draft.tags.map((tag) => (
                  <div key={tag} className={cn("flex items-center gap-1")}>
                    <Tag size="sm" color="gray" title={tag} />
                    <Button
                      size="xs"
                      prominence="tertiary"
                      icon={SvgTrash}
                      disabled={fieldsLocked}
                      aria-label={t("identity.tags.remove.ariaLabel", {
                        tag,
                      })}
                      onClick={() =>
                        onDraftChange({
                          tags: draft.tags.filter((item) => item !== tag),
                        })
                      }
                    />
                  </div>
                ))}
              </div>
              <InputTypeIn
                value={tagDraft}
                placeholder={t("identity.tags.placeholder")}
                variant={fieldsLocked ? "disabled" : "primary"}
                onChange={(event) => setTagDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addTag(tagDraft);
                  }
                }}
              />
              <Button
                size="sm"
                prominence="tertiary"
                icon={SvgPlus}
                disabled={fieldsLocked || !tagDraft.trim()}
                onClick={() => addTag(tagDraft)}
              >
                {t("identity.tags.add.label")}
              </Button>
            </div>
          </InputVertical>
        </div>
      )}
    </EditorSection>
  );
}
