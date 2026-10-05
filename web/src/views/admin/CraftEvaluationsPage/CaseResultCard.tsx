"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Card, Tag, Text } from "@opal/components";
import { SvgBubbleText, SvgCheckCircle, SvgX } from "@opal/icons";
import {
  readFindings,
  readJudgeChecks,
  type CraftEvalCaseResult,
} from "@/lib/craft-evals/types";
import EvalStatusBadge from "./EvalStatusBadge";
import SessionTranscriptModal from "./SessionTranscriptModal";
import { formatDuration, formatScore, getVerdictTagColor } from "./utils";

// ---------------------------------------------------------------------------
// Case result sections
// ---------------------------------------------------------------------------

interface FindingRowProps {
  check: string;
  passed: boolean;
  detail: string;
}

function FindingRow({ check, passed, detail }: FindingRowProps) {
  const Icon = passed ? SvgCheckCircle : SvgX;
  return (
    <li className="flex items-start gap-1.5">
      <Icon
        size={14}
        className={`mt-0.5 shrink-0 ${
          passed ? "text-status-success-05" : "text-status-error-05"
        }`}
      />
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
        <Text font="secondary-mono" color="text-05" wordWrap="wrap-anywhere">
          {check}
        </Text>
        {detail && (
          <Text font="secondary-body" color="text-03" wordWrap="wrap-anywhere">
            {detail}
          </Text>
        )}
      </div>
    </li>
  );
}

interface JudgeCheckRowProps {
  id: string;
  verdict: string;
  evidence: string;
  confidence?: string;
}

function JudgeCheckRow({
  id,
  verdict,
  evidence,
  confidence,
}: JudgeCheckRowProps) {
  return (
    <li className="flex flex-col gap-1 rounded-08 bg-background-tint-01 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <Tag
          title={verdict.toUpperCase()}
          color={getVerdictTagColor(verdict)}
        />
        <Text font="secondary-mono" color="text-05" wordWrap="wrap-anywhere">
          {id}
        </Text>
        {confidence && (
          <Text font="figure-small-label" color="text-04">
            {confidence}
          </Text>
        )}
      </div>
      {evidence && (
        <Text font="secondary-body" color="text-03" wordWrap="wrap-anywhere">
          {evidence}
        </Text>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

interface CaseResultCardProps {
  result: CraftEvalCaseResult;
}

export default function CaseResultCard({ result }: CaseResultCardProps) {
  const t = useTranslations("admin.craft.evaluations");
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  const findings = useMemo(
    () => readFindings(result.deterministic_findings),
    [result.deterministic_findings]
  );
  const checks = useMemo(
    () => readJudgeChecks(result.judge_verdict),
    [result.judge_verdict]
  );
  const judgeErrorValue = result.judge_verdict.error;
  const judgeError =
    typeof judgeErrorValue === "string" ? judgeErrorValue : null;
  const passedFindings = findings.filter((f) => f.passed).length;

  return (
    <Card
      border="solid"
      padding={3}
      rounding={4}
      data-testid={`eval-case-${result.case_slug}`}
    >
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-col gap-0.5">
            <Text font="main-ui-action" color="text-05">
              {result.case_name}
            </Text>
            <Text font="secondary-body" color="text-03" nowrap>
              {`${result.domain} · ${formatDuration(result.duration_seconds)}`}
            </Text>
          </div>
          <div className="flex items-center gap-2">
            {result.session_id && (
              <>
                <Button
                  prominence="tertiary"
                  size="sm"
                  icon={SvgBubbleText}
                  tooltip={result.session_id}
                  onClick={() => setTranscriptOpen(true)}
                >
                  {t("detail.transcript")}
                </Button>
                <SessionTranscriptModal
                  sessionId={transcriptOpen ? result.session_id : null}
                  onClose={() => setTranscriptOpen(false)}
                />
              </>
            )}
            <Text font="main-ui-action" color="text-05">
              {formatScore(result.score)}
            </Text>
            <EvalStatusBadge status={result.status} />
          </div>
        </div>

        {result.error_detail && (
          <div className="rounded-08 bg-status-error-01 p-2">
            <Text
              font="secondary-body"
              color="status-error-05"
              wordWrap="wrap-anywhere"
            >
              {result.error_detail}
            </Text>
          </div>
        )}
        {judgeError && (
          <div className="rounded-08 bg-status-error-01 p-2">
            <Text
              font="secondary-body"
              color="status-error-05"
              wordWrap="wrap-anywhere"
            >
              {`${t("detail.judgeError")}: ${judgeError}`}
            </Text>
          </div>
        )}

        {findings.length > 0 && (
          <div className="flex flex-col gap-1.5" data-testid="eval-findings">
            <div className="uppercase tracking-wide">
              <Text font="figure-small-label" color="text-03">
                {`${t("detail.findings")} (${passedFindings}/${findings.length})`}
              </Text>
            </div>
            <ul className="flex max-h-44 flex-col gap-1.5 overflow-y-auto">
              {findings.map((finding) => (
                <FindingRow
                  key={finding.check}
                  check={finding.check}
                  passed={finding.passed}
                  detail={finding.detail}
                />
              ))}
            </ul>
          </div>
        )}

        {checks.length > 0 && (
          <div
            className="flex flex-col gap-1.5"
            data-testid="eval-judge-checks"
          >
            <div className="uppercase tracking-wide">
              <Text font="figure-small-label" color="text-03">
                {t("detail.judge")}
              </Text>
            </div>
            <ul className="flex flex-col gap-1.5">
              {checks.map((check) => (
                <JudgeCheckRow
                  key={check.id}
                  id={check.id}
                  verdict={check.verdict}
                  evidence={check.evidence}
                  confidence={check.confidence}
                />
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
