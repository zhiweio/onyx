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

export interface ScenarioPlaybookPhase {
  id: string;
  done_when?: string;
}

export interface ScenarioConditionalRule {
  if: {
    query_contains_any?: string[];
    intent?: string;
  };
  add_skill_ids?: string[];
  add_skill_slugs?: string[];
}

export interface ScenarioRules {
  domain?: string;
  always_skill_ids?: string[];
  conditional?: ScenarioConditionalRule[];
  objective?: string;
  required_inputs?: string[];
  phases?: ScenarioPlaybookPhase[];
  deliverables?: string[];
  quality_gates?: string[];
  refusal_rules?: string[];
}

export interface ScenarioPlaybookDraft {
  objective: string;
  required_inputs: string[];
  phases: ScenarioPlaybookPhase[];
  deliverables: string[];
  quality_gates: string[];
  refusal_rules: string[];
}

const PLAYBOOK_KNOWN_KEYS = new Set([
  "domain",
  "always_skill_ids",
  "conditional",
  "objective",
  "required_inputs",
  "phases",
  "deliverables",
  "quality_gates",
  "refusal_rules",
]);

export function emptyPlaybookDraft(): ScenarioPlaybookDraft {
  return {
    objective: "",
    required_inputs: [],
    phases: [],
    deliverables: [],
    quality_gates: [],
    refusal_rules: [],
  };
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item).trim())
    .filter((item) => item.length > 0);
}

function asPhaseList(value: unknown): ScenarioPlaybookPhase[] {
  if (!Array.isArray(value)) return [];
  const phases: ScenarioPlaybookPhase[] = [];
  for (const item of value) {
    if (typeof item === "string" && item.trim()) {
      phases.push({ id: item.trim() });
      continue;
    }
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const id = String(record.id ?? record.name ?? "").trim();
    if (!id) continue;
    const rawDone = record.done_when;
    let done_when: string | undefined;
    if (Array.isArray(rawDone)) {
      done_when = rawDone.map((part) => String(part).trim()).filter(Boolean).join("; ");
    } else if (typeof rawDone === "string" && rawDone.trim()) {
      done_when = rawDone.trim();
    }
    phases.push(done_when ? { id, done_when } : { id });
  }
  return phases;
}

export function parsePlaybookDraft(
  rules: ScenarioRules | Record<string, unknown> | undefined
): { playbook: ScenarioPlaybookDraft; extras: Record<string, unknown> } {
  const raw = (rules ?? {}) as Record<string, unknown>;
  const extras: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (!PLAYBOOK_KNOWN_KEYS.has(key)) {
      extras[key] = value;
    }
  }
  return {
    playbook: {
      objective: typeof raw.objective === "string" ? raw.objective : "",
      required_inputs: asStringList(raw.required_inputs),
      phases: asPhaseList(raw.phases),
      deliverables: asStringList(raw.deliverables),
      quality_gates: asStringList(raw.quality_gates),
      refusal_rules: asStringList(raw.refusal_rules),
    },
    extras,
  };
}

export function playbookToRules(input: {
  domain: string;
  playbook: ScenarioPlaybookDraft;
  extras?: Record<string, unknown>;
  conditionals: ScenarioConditionalRule[];
}): ScenarioRules {
  const conditional = input.conditionals.filter((rule) => {
    const refs = [
      ...(rule.add_skill_ids ?? []),
      ...(rule.add_skill_slugs ?? []),
    ].filter(Boolean);
    return (
      refs.length > 0 &&
      ((rule.if.query_contains_any?.length ?? 0) > 0 || Boolean(rule.if.intent))
    );
  });
  const rules: ScenarioRules & Record<string, unknown> = {
    ...input.extras,
    domain: normalizeScenarioDomain(input.domain),
  };
  const objective = input.playbook.objective.trim();
  if (objective) rules.objective = objective;
  if (input.playbook.required_inputs.length > 0) {
    rules.required_inputs = input.playbook.required_inputs;
  }
  const phases = input.playbook.phases.filter((phase) => phase.id.trim());
  if (phases.length > 0) {
    rules.phases = phases.map((phase) => ({
      id: phase.id.trim(),
      ...(phase.done_when?.trim() ? { done_when: phase.done_when.trim() } : {}),
    }));
  }
  if (input.playbook.deliverables.length > 0) {
    rules.deliverables = input.playbook.deliverables;
  }
  if (input.playbook.quality_gates.length > 0) {
    rules.quality_gates = input.playbook.quality_gates;
  }
  if (input.playbook.refusal_rules.length > 0) {
    rules.refusal_rules = input.playbook.refusal_rules;
  }
  if (conditional.length > 0) {
    rules.conditional = conditional;
  }
  return rules;
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
  const conditional = input.conditionals.filter((rule) => {
    const refs = [
      ...(rule.add_skill_ids ?? []),
      ...(rule.add_skill_slugs ?? []),
    ].filter(Boolean);
    return (
      refs.length > 0 &&
      ((rule.if.query_contains_any?.length ?? 0) > 0 || Boolean(rule.if.intent))
    );
  });
  return {
    domain: normalizeScenarioDomain(input.domain),
    ...(conditional.length > 0 ? { conditional } : {}),
  };
}

export function renderPlaybookSection(rules: ScenarioRules | undefined): string[] {
  if (!rules) return [];
  const lines: string[] = [];
  const objective = rules.objective?.trim();
  if (objective) {
    lines.push("", "## Objective", "", objective);
  }
  if (rules.required_inputs && rules.required_inputs.length > 0) {
    lines.push("", "## Required inputs", "");
    lines.push(
      ...rules.required_inputs
        .filter((item) => item.trim())
        .map((item) => `- ${item}`)
    );
  }
  if (rules.phases && rules.phases.length > 0) {
    lines.push("", "## Phases", "");
    for (const phase of rules.phases) {
      const id = phase.id.trim() || "phase";
      const done = phase.done_when?.trim();
      lines.push(done ? `- **${id}** — done when: ${done}` : `- **${id}**`);
    }
  }
  if (rules.deliverables && rules.deliverables.length > 0) {
    lines.push("", "## Deliverables", "");
    lines.push(
      ...rules.deliverables
        .filter((item) => item.trim())
        .map((item) => `- \`${item}\``)
    );
  }
  if (rules.quality_gates && rules.quality_gates.length > 0) {
    lines.push("", "## Quality gates", "");
    lines.push(
      ...rules.quality_gates
        .filter((item) => item.trim())
        .map((item) => `- ${item}`)
    );
  }
  if (rules.refusal_rules && rules.refusal_rules.length > 0) {
    lines.push("", "## Refusal rules", "");
    lines.push(
      ...rules.refusal_rules
        .filter((item) => item.trim())
        .map((item) => `- ${item}`)
    );
  }
  return lines;
}

export function renderScenarioProtocolPreview(input: {
  name: string;
  description: string;
  skillNames: string[];
  reportTemplate: string | null;
  rules?: ScenarioRules;
}): string {
  const lines = [
    `# Scenario: ${input.name || "…"}`,
    "",
    input.description,
    "",
    "Use only the skills listed below for this session, unless the user asks otherwise.",
    "",
    "## Skills",
  ];
  if (input.skillNames.length > 0) {
    lines.push(...input.skillNames.map((name) => `- ${name}`));
  } else {
    lines.push("- (no skills bound)");
  }
  lines.push(...renderPlaybookSection(input.rules));
  if (input.reportTemplate) {
    lines.push("", `Report template: \`${input.reportTemplate}\``);
  }
  return `${lines.join("\n").trim()}\n`;
}
