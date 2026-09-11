import type {
  ScenarioConditionalRule,
  ScenarioPlaybookDraft,
} from "@/lib/scenarios/types";
import type { SystemCatalogCategory } from "@/lib/system-catalog/types";

export type ScenarioEditorMode = "user" | "catalog";

export interface SkillOption {
  key: string;
  name: string;
  description: string;
}

export interface TemplateOption {
  slug: string;
  name: string;
  description?: string;
}

export interface ConditionalDraft {
  keywords: string;
  intent: string;
  skillKey: string;
}

export interface ScenarioDraft {
  name: string;
  description: string;
  skillKeys: string[];
  reportTemplate: string;
  domain: string;
  playbook: ScenarioPlaybookDraft;
  extras: Record<string, unknown>;
  slug: string;
  category: SystemCatalogCategory;
  tags: string[];
}

export function emptyConditionalDraft(): ConditionalDraft {
  return { keywords: "", intent: "", skillKey: "" };
}

export function conditionalsToRules(
  drafts: ConditionalDraft[],
  keyField: "add_skill_ids" | "add_skill_slugs"
): ScenarioConditionalRule[] {
  return drafts.map((draft) => {
    const keywords = draft.keywords
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    return {
      if: {
        ...(keywords.length > 0 ? { query_contains_any: keywords } : {}),
        ...(draft.intent.trim() ? { intent: draft.intent.trim() } : {}),
      },
      [keyField]: draft.skillKey ? [draft.skillKey] : [],
    };
  });
}

export function draftFingerprint(draft: ScenarioDraft, conditionals: ConditionalDraft[]): string {
  return JSON.stringify({
    name: draft.name,
    description: draft.description,
    skillKeys: draft.skillKeys,
    reportTemplate: draft.reportTemplate,
    domain: draft.domain,
    playbook: draft.playbook,
    extras: draft.extras,
    slug: draft.slug,
    category: draft.category,
    tags: draft.tags,
    conditionals,
  });
}
