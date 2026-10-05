"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CompactMarkdown, Modal, Text } from "@opal/components";
import { SvgBubbleText, SvgSimpleLoader } from "@opal/icons";
import {
  listEvalSessionTranscript,
  type EvalTranscriptEntry,
} from "@/lib/craft-evals/api";

// ---------------------------------------------------------------------------
// Transcript entries
// ---------------------------------------------------------------------------

function TranscriptEntry({ entry }: { entry: EvalTranscriptEntry }) {
  if (entry.role === "tool") {
    return (
      <div className="ps-6">
        <Text font="secondary-body" color="text-04" nowrap>
          {entry.toolLabel ?? "tool"}
        </Text>
      </div>
    );
  }

  if (entry.role === "user") {
    return (
      <div className="max-w-[85%] self-end rounded-08 bg-background-tint-02 px-3 py-2">
        <CompactMarkdown>{entry.content}</CompactMarkdown>
      </div>
    );
  }

  return (
    <div className="max-w-[95%] self-start">
      <CompactMarkdown>{entry.content}</CompactMarkdown>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

interface SessionTranscriptModalProps {
  /** Session to show, or null when closed. */
  sessionId: string | null;
  onClose: () => void;
}

export default function SessionTranscriptModal({
  sessionId,
  onClose,
}: SessionTranscriptModalProps) {
  const t = useTranslations("admin.craft.evaluations");
  const [entries, setEntries] = useState<EvalTranscriptEntry[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const open = sessionId !== null;

  useEffect(() => {
    if (sessionId === null) {
      setEntries(null);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    setEntries(null);
    setLoadError(null);
    listEvalSessionTranscript(sessionId)
      .then((result) => {
        if (!cancelled) {
          setEntries(result);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const visibleEntries = (entries ?? []).filter(
    (entry) => entry.role === "tool" || entry.content.trim().length > 0
  );

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
    >
      <Modal.Content width="lg" height="fit">
        <Modal.Header
          icon={SvgBubbleText}
          title={t("detail.transcriptTitle")}
          description={sessionId ?? undefined}
          onClose={onClose}
        />
        <Modal.Body alignItems="stretch">
          {loadError !== null && (
            <Text font="secondary-body" color="status-error-05">
              {`${t("detail.transcriptFailed")}: ${loadError}`}
            </Text>
          )}
          {loadError === null && entries === null && (
            <div className="flex justify-center py-8">
              <SvgSimpleLoader className="h-6 w-6" />
            </div>
          )}
          {entries !== null && visibleEntries.length === 0 && (
            <Text font="secondary-body" color="text-03">
              {t("detail.transcriptEmpty")}
            </Text>
          )}
          {entries !== null && visibleEntries.length > 0 && (
            <div className="flex flex-col gap-3">
              {visibleEntries.map((entry) => (
                <TranscriptEntry key={entry.id} entry={entry} />
              ))}
            </div>
          )}
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
