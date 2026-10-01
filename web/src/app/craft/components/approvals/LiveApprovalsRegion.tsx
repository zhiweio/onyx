"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";

import { Button, Card, Text } from "@opal/components";
import { SvgAlertTriangle } from "@opal/icons";
import { cn } from "@opal/utils";
import { ContentQuarantineView } from "@/app/craft/types/approvals";
import { postContentQuarantineDecision } from "@/app/craft/services/apiServices";
import ApprovalCard from "@/app/craft/components/approvals/ApprovalCard";
import { useLiveApprovals } from "@/app/craft/hooks/useLiveApprovals";
import { SWR_KEYS } from "@/lib/swr-keys";

type QuarantineTranslate = ReturnType<
  typeof useTranslations<"craft.approvals.quarantine">
>;

interface QuarantineCardProps {
  quarantine: ContentQuarantineView;
}

// Human release decision for one quarantined URL. Approving requires a
// scope: once (next fetch), session (this session), host (30 days). The
// proxy serves the stashed original on the next fetch — no re-crawl.
function QuarantineCard({ quarantine }: QuarantineCardProps) {
  const t = useTranslations("craft.approvals.quarantine");
  const { mutate } = useSWRConfig();
  const [scope, setScope] = useState<"ONCE" | "SESSION" | "HOST">("ONCE");
  const [decided, setDecided] = useState(false);
  const [pendingDecision, setPendingDecision] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "APPROVED" | "DENIED") {
    setPendingDecision(true);
    setError(null);
    try {
      await postContentQuarantineDecision(
        quarantine.quarantine_id,
        decision,
        decision === "APPROVED" ? scope : null
      );
      setDecided(true);
      await mutate(SWR_KEYS.buildSessionLiveApprovals(quarantine.session_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingDecision(false);
    }
  }

  if (decided) {
    return (
      <Card border="solid" rounding={4}>
        <div className="flex items-center gap-2 p-3">
          <SvgAlertTriangle className="h-4 w-4 stroke-text-03" />
          <Text font="secondary-body" color="text-03">
            {t("settled")}
          </Text>
        </div>
      </Card>
    );
  }

  return (
    <Card
      border="solid"
      rounding={4}
      className={cn(pendingDecision && "opacity-60")}
    >
      <div className="flex flex-col gap-2 p-3">
        <div className="flex items-center gap-2">
          <SvgAlertTriangle className="h-4 w-4 shrink-0 stroke-status-warning-05" />
          <Text font="main-ui-action" color="text-05">
            {t("title")}
          </Text>
        </div>
        <Text font="secondary-body" color="text-03" breakWords>
          {t("body", {
            host: quarantine.url_host,
            path: quarantine.url_path,
          })}
        </Text>
        {quarantine.patterns_matched.length > 0 && (
          <Text font="secondary-body" color="text-03">
            {t("patterns", {
              patterns: quarantine.patterns_matched.join(", "),
            })}
          </Text>
        )}
        <div className="flex items-center justify-end gap-2 pt-1">
          <Button
            variant="outline"
            onClick={() => decide("DENIED")}
            disabled={pendingDecision}
          >
            {t("deny")}
          </Button>
          <Button
            variant="action"
            onClick={() => decide("APPROVED")}
            disabled={pendingDecision}
          >
            {t("approve", {
              scope:
                scope === "ONCE"
                  ? t("scope.once")
                  : scope === "SESSION"
                    ? t("scope.session")
                    : t("scope.host"),
            })}
          </Button>
        </div>
        <div className="flex items-center gap-2 pt-1">
          {(["ONCE", "SESSION", "HOST"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setScope(s)}
              className={cn(
                "rounded-08 px-2 py-1 text-xs",
                scope === s
                  ? "bg-action-selection-04 text-inverted"
                  : "bg-background-neutral-01 text-text-03"
              )}
            >
              {t(`scope.${s.toLowerCase()}`)}
            </button>
          ))}
        </div>
        {error && (
          <Text font="secondary-body" color="text-status-error-05">
            {error}
          </Text>
        )}
      </div>
    </Card>
  );
}

interface LiveApprovalsRegionProps {
  sessionId: string | null;
}

// Renders one ApprovalCard per row returned by /live (already filtered
// to undecided + within wait window), plus one release card per undecided
// inbound-content quarantine. No outer logo/wrapper — caller is
// responsible for placing this inside the previous assistant message
// region so cards visually attach to the agent's last turn.
//
// SWR cache invalidation is owned by useBuildStreaming's
// approval_requested handler and by ApprovalCard itself after a
// decision — this component just reads.
export default function LiveApprovalsRegion({
  sessionId,
}: LiveApprovalsRegionProps) {
  const t = useTranslations("craft.approvals.quarantine");
  const { data } = useLiveApprovals(sessionId);

  if (!sessionId || !data) {
    return null;
  }

  const quarantines = data.content_quarantines ?? [];

  if (data.items.length === 0 && quarantines.length === 0) {
    return null;
  }

  const sorted = [...data.items].sort(
    (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at)
  );

  return (
    <div data-testid="live-approvals-region" className="flex flex-col gap-3">
      {sorted.map((approval) => (
        <ApprovalCard key={approval.approval_id} approval={approval} />
      ))}
      {quarantines.map((quarantine) => (
        <QuarantineCard
          key={quarantine.quarantine_id}
          quarantine={quarantine}
        />
      ))}
    </div>
  );
}
