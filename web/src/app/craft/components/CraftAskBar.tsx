"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Text } from "@opal/components";
import type { CraftJobResponse } from "@/app/craft/services/apiServices";

export type AskBarAction = "approve" | "revise" | "reject";

const REJECT_OPTION_RE =
  /^(cancel|reject|decline|no|skip|拒绝|取消|否)$/i;

function isRejectOption(option: string): boolean {
  return REJECT_OPTION_RE.test(option.trim());
}

export interface QuestionAskItemView {
  prompt: string;
  options: string[];
}

export interface QuestionAskView {
  requestId: string;
  prompt: string;
  options: string[];
  questions?: QuestionAskItemView[];
}

export function CraftAskBar({
  job,
  question,
  onJobAction,
  onQuestionAnswer,
}: {
  job?: CraftJobResponse | null;
  question?: QuestionAskView | null;
  onJobAction?: (action: AskBarAction) => Promise<void> | void;
  onQuestionAnswer?: (
    requestId: string,
    allow: boolean,
    answers?: string[][]
  ) => Promise<void> | void;
}) {
  const t = useTranslations("craft.longJob.askBar");
  const [busy, setBusy] = useState(false);

  const waitingJob =
    job?.status === "interrupted" &&
    (job.interrupt?.kind === "approve_plan" ||
      job.interrupt?.kind === "approve_delivery" ||
      job.interrupt?.kind === "clarify");

  if (!waitingJob && !question) {
    return null;
  }

  const kind = job?.interrupt?.kind ?? "";
  const payload = job?.interrupt?.payload ?? {};
  const summary =
    (typeof payload.summary === "string" && payload.summary) ||
    (typeof payload.goal === "string" && payload.goal) ||
    job?.name ||
    "";
  const steps = Array.isArray(payload.steps)
    ? payload.steps.filter((item): item is string => typeof item === "string")
    : [];

  const run = async (work: () => Promise<void> | void) => {
    if (busy) return;
    setBusy(true);
    try {
      await work();
    } finally {
      setBusy(false);
    }
  };

  if (question) {
    return (
      <QuestionAskChips
        key={question.requestId}
        question={question}
        busy={busy}
        run={run}
        onQuestionAnswer={onQuestionAnswer}
      />
    );
  }

  const isDelivery = kind === "approve_delivery";
  return (
    <div
      className="mb-2 flex min-w-0 flex-col gap-2 rounded-12 border border-border-01 bg-background-neutral-00 p-2"
      data-testid="craft-ask-bar"
    >
      <Text font="main-ui-action" color="text-04">
        {isDelivery ? t("reviewResult") : t("needChoice")}
      </Text>
      {summary ? (
        <Text font="secondary-body" color="text-03">
          {summary}
        </Text>
      ) : null}
      {steps.length > 0 ? (
        <Text font="secondary-body" color="text-03">
          {steps.join(" · ")}
        </Text>
      ) : null}
      <div className="flex min-w-0 flex-wrap gap-1">
        <Button
          type="button"
          size="xs"
          prominence="secondary"
          data-testid="craft-ask-approve"
          disabled={busy}
          onClick={() => void run(() => onJobAction?.("approve"))}
        >
          {isDelivery ? t("accept") : t("start")}
        </Button>
        <Button
          type="button"
          size="xs"
          prominence="tertiary"
          data-testid="craft-ask-revise"
          disabled={busy}
          onClick={() => void run(() => onJobAction?.("revise"))}
        >
          {isDelivery ? t("requestChanges") : t("changeDirection")}
        </Button>
        <Button
          type="button"
          size="xs"
          prominence="tertiary"
          data-testid="craft-ask-cancel"
          disabled={busy}
          onClick={() => void run(() => onJobAction?.("reject"))}
        >
          {t("cancel")}
        </Button>
      </div>
    </div>
  );
}

function QuestionAskChips({
  question,
  busy,
  run,
  onQuestionAnswer,
}: {
  question: QuestionAskView;
  busy: boolean;
  run: (work: () => Promise<void> | void) => Promise<void>;
  onQuestionAnswer?: (
    requestId: string,
    allow: boolean,
    answers?: string[][]
  ) => Promise<void> | void;
}) {
  const t = useTranslations("craft.longJob.askBar");
  const items =
    question.questions && question.questions.length > 0
      ? question.questions
      : [{ prompt: question.prompt, options: question.options }];
  const [step, setStep] = useState(0);
  const [picked, setPicked] = useState<string[][]>([]);
  const current = items[Math.min(step, items.length - 1)] ?? items[0];
  const options =
    current && current.options.length > 0
      ? current.options
      : [t("continue"), t("changeDirection"), t("cancel")];

  return (
    <div
      className="mb-2 flex min-w-0 flex-col gap-2 rounded-12 border border-border-01 bg-background-neutral-00 p-2"
      data-testid="craft-ask-bar"
    >
      <Text font="main-ui-action" color="text-04">
        {current?.prompt || question.prompt || t("needChoice")}
      </Text>
      {items.length > 1 ? (
        <Text font="secondary-body" color="text-03">
          {`${Math.min(step, items.length - 1) + 1} / ${items.length}`}
        </Text>
      ) : null}
      <div className="flex min-w-0 flex-wrap gap-1">
        {options.map((option) => (
          <Button
            key={`${step}-${option}`}
            type="button"
            size="xs"
            prominence="secondary"
            disabled={busy}
            onClick={() =>
              void run(() => {
                if (isRejectOption(option)) {
                  return onQuestionAnswer?.(question.requestId, false);
                }
                const next = [...picked, [option]];
                if (next.length >= items.length) {
                  return onQuestionAnswer?.(question.requestId, true, next);
                }
                setPicked(next);
                setStep(next.length);
              })
            }
          >
            {option}
          </Button>
        ))}
        <Button
          type="button"
          size="xs"
          prominence="tertiary"
          data-testid="craft-ask-reject"
          disabled={busy}
          onClick={() =>
            void run(() => onQuestionAnswer?.(question.requestId, false))
          }
        >
          {t("reject")}
        </Button>
      </div>
    </div>
  );
}

export default CraftAskBar;
