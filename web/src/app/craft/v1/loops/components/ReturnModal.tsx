"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  BasicModalFooter,
  Button,
  InputTextArea,
  Modal,
  Text,
} from "@opal/components";
import { toast } from "@opal/layouts";
import { SvgArrowLeft } from "@opal/icons";
import { decideLoopOutput } from "@/app/craft/v1/loops/api";
import type { LoopOutput } from "@/app/craft/v1/loops/interfaces";

interface ReturnModalProps {
  loopId: string;
  output: LoopOutput | null;
  onClose: () => void;
  onDecided: () => void | Promise<void>;
}

/** Return a held output to work with an optional guidance note. */
export default function ReturnModal({
  loopId,
  output,
  onClose,
  onDecided,
}: ReturnModalProps) {
  const t = useTranslations("craft.loops.detailPage.returnModal");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (output) setNote("");
  }, [output]);

  async function handleReturn() {
    if (!output) return;
    setSaving(true);
    try {
      await decideLoopOutput(
        loopId,
        output.id,
        "return",
        note.trim() || undefined
      );
      toast.success(t("toasts.returned"));
      onClose();
      await onDecided();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("toasts.failed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={output !== null}
      onOpenChange={(next) => {
        if (!next && !saving) onClose();
      }}
    >
      <Modal.Content width="sm">
        <Modal.Header
          icon={SvgArrowLeft}
          title={t("title")}
          onClose={() => {
            if (!saving) onClose();
          }}
        />
        <Modal.Body>
          <div className="flex w-full flex-col gap-3">
            <Text font="secondary-body" color="text-03">
              {output?.title}
            </Text>
            <InputTextArea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder={t("notePlaceholder")}
              data-testid="return-note-input"
            />
            <Text font="secondary-body" color="text-03">
              {t("hint")}
            </Text>
          </div>
        </Modal.Body>
        <BasicModalFooter
          cancel={
            <Button
              variant="default"
              prominence="secondary"
              onClick={onClose}
              disabled={saving}
            >
              {t("cancelButton")}
            </Button>
          }
          submit={
            <Button
              variant="default"
              prominence="primary"
              onClick={() => void handleReturn()}
              disabled={saving}
              data-testid="confirm-return-output"
            >
              {saving ? t("returningButton") : t("returnButton")}
            </Button>
          }
        />
      </Modal.Content>
    </Modal>
  );
}
