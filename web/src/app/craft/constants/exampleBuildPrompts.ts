import type { IconFunctionComponent } from "@opal/types";
import {
  SvgLineChartUp,
  SvgBullhorn,
  SvgCode,
  SvgLightbulbSimple,
  SvgPieChart,
} from "@opal/icons";

export interface BuildPrompt {
  id: string;
  /** Sentence-length description shown in the expanded prompt list */
  summary: string;
  /** Full prompt text inserted into the input bar */
  fullText: string;
}

export interface UseCaseDomain {
  id: string;
  label: string;
  icon: IconFunctionComponent;
  prompts: BuildPrompt[];
}

export const useCaseDomains: UseCaseDomain[] = [
  {
    id: "financeTax",
    label: "Finance & Tax",
    icon: SvgPieChart,
    prompts: [
      {
        id: "finance-monthly-review-deck",
        summary: "把本月三大报表做成管理层汇报演示",
        fullText:
          "根据我上传的本月利润表、资产负债表和费用明细，做一份月度经营财税汇报演示：收入利润概览、费用异动归因、税负与现金流、风险提示和行动项。",
      },
      {
        id: "finance-policy-briefing-deck",
        summary: "解读最新财税新政，产出宣讲演示",
        fullText:
          "解读这份最新财税政策文件，做一份面向业务团队的宣讲演示：政策要点、前后对照、对我们的影响、应对动作和时间表。",
      },
      {
        id: "finance-compliance-check",
        summary: "给公司做一次税务合规体检",
        fullText:
          "为我们公司做一次税务合规体检：申报一致性、税负合理性、内控有效性、舞弊红旗、税收优惠备案五块逐项检查，出具体检报告和整改清单。",
      },
      {
        id: "finance-vat-workpaper",
        summary: "准备增值税申报底稿和检查清单",
        fullText:
          "根据发票台账和本月账簿，准备增值税申报底稿：进销项勾稽、税额计算、适用税率核验，并生成提交前检查清单。",
      },
    ],
  },
  {
    id: "engineering",
    label: "Engineering",
    icon: SvgCode,
    prompts: [
      {
        id: "eng-oncall",
        summary:
          "Track on-call rotations and post each week's schedule to Slack",
        fullText:
          "Spin up an on-call rotation tracker from PagerDuty and Slack. Every week send a message in Slack for who is on-call for the week.",
      },
      {
        id: "eng-sprint-health",
        summary: "Build a sprint health dashboard from your Linear cycle data",
        fullText:
          "Build a sprint health dashboard from your Linear cycle data.",
      },
      {
        id: "eng-release-notes",
        summary: "Generate release notes from a milestone's merged PRs",
        fullText: "Generate release notes from this milestone's merged PRs.",
      },
    ],
  },
  {
    id: "sales",
    label: "Sales",
    icon: SvgLineChartUp,
    prompts: [
      {
        id: "sales-account-brief",
        summary:
          "Build a one-page account brief before every call from Salesforce, Slack, and Gong",
        fullText:
          "Build a one-page account brief before every call — from Salesforce, Slack, and Gong.",
      },
      {
        id: "sales-winloss",
        summary:
          "Turn this quarter's closed-won deals into a win/loss dashboard",
        fullText:
          "Turn this quarter's closed-won deals into a win/loss dashboard.",
      },
      {
        id: "sales-battlecard",
        summary:
          "Build a competitor battlecard from recent lost-deal call transcripts",
        fullText:
          "Build a competitor battlecard from recent lost-deal call transcripts.",
      },
      {
        id: "sales-pipeline-tracker",
        summary:
          "Spin up a pipeline tracker that flags deals with no activity in 14 days",
        fullText:
          "Spin up a pipeline tracker that flags deals with no activity in 14 days.",
      },
    ],
  },
  {
    id: "marketing",
    label: "Marketing",
    icon: SvgBullhorn,
    prompts: [
      {
        id: "marketing-seo",
        summary:
          "Turn sales-call transcripts into an SEO keyword research report",
        fullText:
          "Turn sales-call transcripts into an SEO keyword research report.",
      },
      {
        id: "marketing-customer-story",
        summary:
          "Assemble a customer-story one-pager from interview transcripts",
        fullText:
          "Assemble a customer-story one-pager from interview transcripts.",
      },
      {
        id: "marketing-social-posts",
        summary: "Draft on-brand social posts from this product launch doc",
        fullText: "Draft on-brand social posts from this product launch doc.",
      },
    ],
  },
  {
    id: "product",
    label: "Product",
    icon: SvgLightbulbSimple,
    prompts: [
      {
        id: "product-daily-brief",
        summary:
          "Brief me on everything that happened across my projects today",
        fullText:
          "Brief me for the day — tell me everything that happened for every project I was working on.",
      },
      {
        id: "product-prototype",
        summary: "Turn this PRD into a clickable prototype to test with users",
        fullText:
          "Turn this PRD into a clickable prototype to test with users.",
      },
      {
        id: "product-roadmap",
        summary: "Spin up a roadmap tracker from your Linear projects",
        fullText: "Spin up a roadmap tracker from your Linear projects.",
      },
      {
        id: "product-feature-matrix",
        summary: "Build a competitor feature-comparison matrix",
        fullText: "Build a competitor feature-comparison matrix.",
      },
    ],
  },
];
