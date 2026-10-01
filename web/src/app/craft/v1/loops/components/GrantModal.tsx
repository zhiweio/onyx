"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  BasicModalFooter,
  Button,
  InputTypeIn,
  MessageCard,
  Modal,
} from "@opal/components";
import { InputVertical, toast } from "@opal/layouts";
import { SvgShield } from "@opal/icons";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { createLoopGrant } from "@/app/craft/v1/loops/api";
import type { ShipActionSpec } from "@/app/craft/v1/loops/interfaces";

interface GrantModalProps {
  loopId: string;
  /** Ship actions declared on the loop; free entry when empty. */
  shipActions: ShipActionSpec[];
  open: boolean;
  onClose: () => void;
  onGranted: () => void | Promise<void>;
}

/** Issue a standing grant (graduation) for one ship action. */
export default function GrantModal({
  loopId,
  shipActions,
  open,
  onClose,
  onGranted,
}: GrantModalProps) {
  const t = useTranslations("craft.loops.detailPage.grantModal");
  const [action, setAction] = useState("");
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);

  useEffect(() => {
    if (!open) return;
    setAction(shipActions[0]?.action ?? "");
    setLabel("");
    setSubmitAttempted(false);
  }, [open, shipActions]);

  const actionError = action.trim() ? null : t("errors.actionRequired");
  const canSave = !actionError && !saving;

  async function handleGrant() {
    setSubmitAttempted(true);
    if (!canSave) return;
    setSaving(true);
    try {
      await createLoopGrant(loopId, action.trim(), label.trim() || null);
      toast.success(t("toasts.granted"));
      onClose();
      await onGranted();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("toasts.failed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next && !saving) onClose();
      }}
    >
      <Modal.Content width="sm">
        <Modal.Header
          icon={SvgShield}
          title={t("title")}
          onClose={() => {
            if (!saving) onClose();
          }}
        />
        <Modal.Body>
          <form
            id="loop-grant-form"
            className="flex w-full flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void handleGrant();
            }}
          >
            <InputVertical withLabel title={t("fields.action.label")}>
              {shipActions.length > 0 ? (
                <InputSelect value={action} onValueChange={setAction}>
                  <InputSelect.Trigger />
                  <InputSelect.Content>
                    {shipActions.map((spec) => (
                      <InputSelect.Item key={spec.action} value={spec.action}>
                        {spec.action}
                      </InputSelect.Item>
                    ))}
                  </InputSelect.Content>
                </InputSelect>
              ) : (
                <InputTypeIn
                  value={action}
                  onChange={(e) => setAction(e.target.value)}
                  placeholder={t("fields.action.placeholder")}
                  data-testid="grant-action-input"
                />
              )}
            </InputVertical>

            <InputVertical
              withLabel
              title={t("fields.label.label")}
              description={t("fields.label.description")}
            >
              <InputTypeIn
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder={t("fields.label.placeholder")}
                data-testid="grant-label-input"
              />
            </InputVertical>

            {submitAttempted && actionError && (
              <MessageCard
                variant="error"
                title={t("errors.title")}
                description={actionError}
              />
            )}
          </form>
        </Modal.Body>
        <Modal.Footer>
          <BasicModalFooter
            cancel={
              <Button
                prominence="secondary"
                type="button"
                disabled={saving}
                onClick={onClose}
              >
                {t("cancelButton")}
              </Button>
            }
            submit={
              <Button
                type="submit"
                form="loop-grant-form"
                disabled={saving}
                data-testid="grant-submit"
              >
                {t("grantButton")}
              </Button>
            }
          />
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
