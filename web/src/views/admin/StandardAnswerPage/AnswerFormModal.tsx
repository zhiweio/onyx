"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  BasicModalFooter,
  Button,
  Checkbox,
  InputSelect,
  InputTextArea,
  InputTypeIn,
  MessageCard,
  Modal,
  Text,
} from "@opal/components";
import { InputVertical, toast } from "@opal/layouts";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import {
  createStandardAnswer,
  updateStandardAnswer,
  type StandardAnswerCategoryRow,
  type StandardAnswerRow,
} from "./api";

interface AnswerFormModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
  categories: StandardAnswerCategoryRow[];
  /** ``null`` creates a new answer; a row edits it. */
  initial: StandardAnswerRow | null;
}

interface AnswerDraft {
  keyword: string;
  answer: string;
  categoryId: string;
  matchRegex: boolean;
}

const NONE_CATEGORY = "__none__";

export default function AnswerFormModal({
  open,
  onClose,
  onSaved,
  categories,
  initial,
}: AnswerFormModalProps) {
  const t = useTranslations("admin.standardAnswers");
  const [draft, setDraft] = useState<AnswerDraft>({
    keyword: "",
    answer: "",
    categoryId: NONE_CATEGORY,
    matchRegex: false,
  });
  const [saving, setSaving] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const keywordInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setDraft({
      keyword: initial?.keyword ?? "",
      answer: initial?.answer ?? "",
      categoryId: initial?.category_ids[0]
        ? String(initial.category_ids[0])
        : NONE_CATEGORY,
      matchRegex: initial?.match_regex ?? false,
    });
    setSubmitAttempted(false);
    keywordInputRef.current?.focus();
  }, [open, initial]);

  const keywordError = draft.keyword.trim()
    ? null
    : t("form.errors.keywordRequired");
  const answerError = draft.answer.trim()
    ? null
    : t("form.errors.answerRequired");
  const canSave = !keywordError && !answerError && !saving;

  async function handleSave() {
    setSubmitAttempted(true);
    if (!canSave) return;
    setSaving(true);
    const categoryIds =
      draft.categoryId !== NONE_CATEGORY ? [Number(draft.categoryId)] : [];
    try {
      if (initial) {
        await updateStandardAnswer(initial.id, {
          keyword: draft.keyword.trim(),
          answer: draft.answer,
          match_regex: draft.matchRegex,
          category_ids: categoryIds,
        });
        toast.success(t("updated"));
      } else {
        await createStandardAnswer({
          keyword: draft.keyword.trim(),
          answer: draft.answer,
          match_regex: draft.matchRegex,
          category_ids: categoryIds,
        });
        toast.success(t("created"));
      }
      onClose();
      await onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
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
      <Modal.Content width="md">
        <Modal.Header
          icon={ADMIN_ROUTES.STANDARD_ANSWERS.icon}
          title={initial ? t("form.editTitle") : t("form.createTitle")}
          description={t("form.description")}
          onClose={() => {
            if (!saving) onClose();
          }}
        />
        <Modal.Body>
          <form
            id="standard-answer-form"
            className="flex w-full flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSave();
            }}
          >
            <InputVertical withLabel title={t("form.keyword")}>
              <InputTypeIn
                ref={keywordInputRef}
                value={draft.keyword}
                onChange={(e) =>
                  setDraft({ ...draft, keyword: e.target.value })
                }
                placeholder={t("form.keywordPlaceholder")}
                data-testid="standard-answer-keyword-input"
              />
            </InputVertical>

            <InputVertical withLabel title={t("form.answer")}>
              <InputTextArea
                value={draft.answer}
                onChange={(e) => setDraft({ ...draft, answer: e.target.value })}
                placeholder={t("form.answerPlaceholder")}
                data-testid="standard-answer-answer-input"
              />
            </InputVertical>

            {categories.length > 0 ? (
              <InputVertical withLabel title={t("form.category")}>
                <InputSelect
                  value={draft.categoryId}
                  onValueChange={(value) =>
                    setDraft({ ...draft, categoryId: value })
                  }
                >
                  <InputSelect.Trigger placeholder={t("form.category")} />
                  <InputSelect.Content>
                    <InputSelect.Item value={NONE_CATEGORY}>
                      {t("form.noCategory")}
                    </InputSelect.Item>
                    {categories.map((category) => (
                      <InputSelect.Item
                        key={category.id}
                        value={String(category.id)}
                      >
                        {category.name}
                      </InputSelect.Item>
                    ))}
                  </InputSelect.Content>
                </InputSelect>
              </InputVertical>
            ) : null}

            <InputVertical withLabel title={t("form.matchRegex.label")}>
              <label
                className="flex cursor-pointer items-center gap-2"
                htmlFor="standard-answer-match-regex"
              >
                <Checkbox
                  id="standard-answer-match-regex"
                  checked={draft.matchRegex}
                  onCheckedChange={() =>
                    setDraft({ ...draft, matchRegex: !draft.matchRegex })
                  }
                />
                <Text font="secondary-body">
                  {t("form.matchRegex.description")}
                </Text>
              </label>
            </InputVertical>

            {submitAttempted && (keywordError || answerError) && (
              <MessageCard
                variant="error"
                title={t("form.errors.title")}
                description={keywordError ?? answerError ?? ""}
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
                {t("form.cancel")}
              </Button>
            }
            submit={
              <Button
                type="submit"
                form="standard-answer-form"
                disabled={!canSave}
                data-testid="standard-answer-save"
              >
                {initial ? t("form.submitEdit") : t("form.submitCreate")}
              </Button>
            }
          />
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
