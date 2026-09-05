export type ScenarioAccessLevel = "OWNER" | "EDITOR" | "VIEWER";
export type ScenarioSharePermission = "EDITOR" | "VIEWER";
export const BUILTIN_SCENARIO_DOMAINS = ["tax", "biomed"] as const;
export type BuiltinScenarioDomain = (typeof BUILTIN_SCENARIO_DOMAINS)[number];
export type ScenarioDomain = string;
export const UNCATEGORIZED_SCENARIO_DOMAIN = "custom";

export interface ScenarioSkillRef {
  skill_id: string;
  sort_order: number;
}

export interface ScenarioConditionalRule {
  if: {
    query_contains_any?: string[];
    intent?: string;
  };
  add_skill_ids: string[];
}

export interface ScenarioRules {
  domain?: string;
  always_skill_ids?: string[];
  conditional?: ScenarioConditionalRule[];
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  author_user_id: string | null;
  public_permission: ScenarioSharePermission | null;
  rules: ScenarioRules;
  report_template: string | null;
  skill_ids: string[];
  skills: ScenarioSkillRef[];
  access_level: ScenarioAccessLevel;
  shared_user_ids: string[];
  shared_group_ids: number[];
}

export interface ScenarioListResponse {
  scenarios: Scenario[];
}

export function isBuiltinScenarioDomain(
  domain: string
): domain is BuiltinScenarioDomain {
  return domain === "tax" || domain === "biomed";
}

export function isUncategorizedDomain(domain: string): boolean {
  return domain.trim() === "" || domain === UNCATEGORIZED_SCENARIO_DOMAIN;
}

export function normalizeScenarioDomain(domain: string | undefined): string {
  if (typeof domain !== "string") {
    return UNCATEGORIZED_SCENARIO_DOMAIN;
  }
  const trimmed = domain.trim();
  return trimmed.length > 0 ? trimmed : UNCATEGORIZED_SCENARIO_DOMAIN;
}

export function scenarioDomainMessageKey(
  domain: BuiltinScenarioDomain | "all" | typeof UNCATEGORIZED_SCENARIO_DOMAIN
):
  | "domain.all.label"
  | "domain.tax.label"
  | "domain.biomed.label"
  | "domain.custom.label" {
  switch (domain) {
    case "all":
      return "domain.all.label";
    case "tax":
      return "domain.tax.label";
    case "biomed":
      return "domain.biomed.label";
    case "custom":
      return "domain.custom.label";
  }
}

export function scenarioDomain(scenario: Scenario): string {
  return normalizeScenarioDomain(scenario.rules?.domain);
}

export function collectCustomScenarioDomains(scenarios: Scenario[]): string[] {
  const names = new Set<string>();
  for (const scenario of scenarios) {
    const domain = scenarioDomain(scenario);
    if (!isBuiltinScenarioDomain(domain) && !isUncategorizedDomain(domain)) {
      names.add(domain);
    }
  }
  return Array.from(names).sort((left, right) => left.localeCompare(right));
}

export function scenarioDomainTagColor(
  domain: string
): "blue" | "purple" | "gray" {
  if (domain === "tax") return "blue";
  if (domain === "biomed") return "purple";
  return "gray";
}

export function canEditScenario(scenario: Scenario): boolean {
  return scenario.access_level === "OWNER" || scenario.access_level === "EDITOR";
}

export function isWorkspaceScenario(scenario: Scenario): boolean {
  return scenario.author_user_id === null;
}

export function buildScenarioRules(input: {
  domain: string;
  conditionals: ScenarioConditionalRule[];
}): ScenarioRules {
  const conditional = input.conditionals.filter(
    (rule) =>
      rule.add_skill_ids.length > 0 &&
      ((rule.if.query_contains_any?.length ?? 0) > 0 || Boolean(rule.if.intent))
  );
  return {
    domain: normalizeScenarioDomain(input.domain),
    ...(conditional.length > 0 ? { conditional } : {}),
  };
}

export function renderScenarioProtocolPreview(input: {
  name: string;
  description: string;
  skillNames: string[];
  reportTemplate: string | null;
}): string {
  const lines = [
    `# Scenario: ${input.name || "…"}`,
    "",
    input.description,
    "",
    "Use only these skills unless the user asks otherwise:",
    "",
  ];
  if (input.skillNames.length > 0) {
    lines.push(...input.skillNames.map((name) => `- ${name}`));
  } else {
    lines.push("- (no skills bound)");
  }
  if (input.reportTemplate) {
    lines.push("", `Preferred report template: \`${input.reportTemplate}\``);
  }
  return `${lines.join("\n").trim()}\n`;
}
