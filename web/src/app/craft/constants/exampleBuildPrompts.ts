import type { IconFunctionComponent } from "@opal/types";
import {
  SvgLineChartUp,
  SvgBullhorn,
  SvgCode,
  SvgLightbulbSimple,
  SvgPieChart,
} from "@opal/icons";

/**
 * Scenario tools an example prompt preselects when clicked. References are
 * matched loosely (case-insensitive substring against the skill slug / MCP
 * server name) and resolve to nothing when the deployment lacks them, so a
 * prompt never breaks because its tools are absent.
 */
export interface PromptToolHints {
  skillSlugs?: string[];
  mcpServerNames?: string[];
  webSearch?: boolean;
}

export interface BuildPrompt {
  id: string;
  toolHints?: PromptToolHints;
}

export interface UseCaseDomain {
  id: string;
  icon: IconFunctionComponent;
  prompts: BuildPrompt[];
}

/**
 * Display copy lives in the `craft.suggestedPrompts` messages — label at
 * `.<domainId>.label`, prompt text at `.<domainId>.prompts.<promptId>.summary`
 * and `.fullText` — so examples follow the interface language.
 */
export const useCaseDomains: UseCaseDomain[] = [
  {
    id: "financeTax",
    icon: SvgPieChart,
    prompts: [
      {
        id: "finance-monthly-review-deck",
        toolHints: { mcpServerNames: ["finance", "财税"] },
      },
      {
        id: "finance-policy-briefing-deck",
        toolHints: { webSearch: true, mcpServerNames: ["finance", "财税"] },
      },
      {
        id: "finance-compliance-check",
        toolHints: { mcpServerNames: ["finance", "财税"] },
      },
      {
        id: "finance-vat-workpaper",
        toolHints: { mcpServerNames: ["finance", "财税"] },
      },
    ],
  },
  {
    id: "engineering",
    icon: SvgCode,
    prompts: [
      {
        id: "eng-oncall",
        toolHints: { mcpServerNames: ["pagerduty", "slack"] },
      },
      {
        id: "eng-sprint-health",
        toolHints: { mcpServerNames: ["linear"] },
      },
      {
        id: "eng-release-notes",
        toolHints: { mcpServerNames: ["github"] },
      },
    ],
  },
  {
    id: "sales",
    icon: SvgLineChartUp,
    prompts: [
      {
        id: "sales-account-brief",
        toolHints: { mcpServerNames: ["salesforce", "slack", "gong"] },
      },
      {
        id: "sales-winloss",
        toolHints: { mcpServerNames: ["salesforce"] },
      },
      {
        id: "sales-battlecard",
        toolHints: { mcpServerNames: ["gong"] },
      },
      {
        id: "sales-pipeline-tracker",
        toolHints: { mcpServerNames: ["salesforce"] },
      },
    ],
  },
  {
    id: "marketing",
    icon: SvgBullhorn,
    prompts: [
      {
        id: "marketing-seo",
        toolHints: { webSearch: true },
      },
      {
        id: "marketing-customer-story",
      },
      {
        id: "marketing-social-posts",
      },
    ],
  },
  {
    id: "product",
    icon: SvgLightbulbSimple,
    prompts: [
      {
        id: "product-daily-brief",
      },
      {
        id: "product-prototype",
      },
      {
        id: "product-roadmap",
        toolHints: { mcpServerNames: ["linear"] },
      },
      {
        id: "product-feature-matrix",
        toolHints: { webSearch: true },
      },
    ],
  },
];

/** A prompt ready to hand to a surface, with its scenario tool hints. */
export interface ExamplePromptSelection {
  domainId: string;
  promptId: string;
  fullText: string;
  toolHints?: PromptToolHints;
}
