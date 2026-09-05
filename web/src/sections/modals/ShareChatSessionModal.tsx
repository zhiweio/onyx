"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ChatSession, ChatSessionSharedStatus } from "@/app/app/interfaces";
import { useChatSessionStore } from "@/app/app/stores/useChatSessionStore";
import { copyAll } from "@/app/app/message/copyingUtils";
import { Section } from "@/layouts/general-layouts";
import { Modal } from "@opal/components";
import { Button, CopyButton, InputTypeIn, SelectCard } from "@opal/components";
import { ContentAction, toast } from "@opal/layouts";
import { SvgLink, SvgShare, SvgUser, SvgUsers } from "@opal/icons";
import SvgCheck from "@opal/icons/check";
import SvgLock from "@opal/icons/lock";

import type { IconProps } from "@opal/types";
import useChatSessions from "@/hooks/useChatSessions";
import useShareableGroups, {
  type MinimalUserGroupSnapshot,
} from "@/hooks/useShareableGroups";
import useShareableUsers from "@/hooks/useShareableUsers";
import type { MinimalUserSnapshot } from "@/lib/types";
import { AddPeoplePicker } from "@/sections/modals/AddPeoplePicker";

function buildShareLink(chatSessionId: string) {
  const baseUrl = `${window.location.protocol}//${window.location.host}`;
  return `${baseUrl}/app/shared/${chatSessionId}`;
}

async function generateShareLink(chatSessionId: string) {
  const response = await fetch(`/api/chat/chat-session/${chatSessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sharing_status: "public" }),
  });

  if (response.ok) {
    return buildShareLink(chatSessionId);
  }
  return null;
}

async function deleteShareLink(chatSessionId: string) {
  const response = await fetch(`/api/chat/chat-session/${chatSessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sharing_status: "private",
      shared_user_ids: [],
      shared_group_ids: [],
    }),
  });

  return response.ok;
}

async function saveMemberShares(
  chatSessionId: string,
  userIds: string[],
  groupIds: number[]
) {
  const response = await fetch(`/api/chat/chat-session/${chatSessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sharing_status: "shared",
      shared_user_ids: userIds,
      shared_group_ids: groupIds,
    }),
  });
  return response.ok;
}

interface PrivacyOptionProps {
  icon: React.FunctionComponent<IconProps>;
  title: string;
  description: string;
  selected: boolean;
  onClick: () => void;
  ariaLabel?: string;
}

function PrivacyOption({
  icon: Icon,
  title,
  description,
  selected,
  onClick,
  ariaLabel,
}: PrivacyOptionProps) {
  return (
    <SelectCard
      state={selected ? "filled" : "empty"}
      padding={2}
      rounding={2}
      border="none"
      onClick={onClick}
      aria-label={ariaLabel}
    >
      <ContentAction
        sizePreset="main-ui"
        variant="section"
        icon={Icon}
        title={title}
        description={description}
        padding={0}
        color="interactive"
        rightChildren={
          selected ? (
            <SvgCheck
              size={16}
              className="shrink-0 stroke-action-selection-05"
            />
          ) : undefined
        }
      />
    </SelectCard>
  );
}

type PrivacyChoice = "private" | "public" | "people";

interface ShareChatSessionModalProps {
  chatSession: ChatSession;
  onClose: () => void;
}

export default function ShareChatSessionModal({
  chatSession,
  onClose,
}: ShareChatSessionModalProps) {
  const t = useTranslations("chat.modals.share");
  const isCurrentlyPublic =
    chatSession.shared_status === ChatSessionSharedStatus.Public;
  const isCurrentlyMembers =
    chatSession.shared_status === ChatSessionSharedStatus.Shared;

  const [selectedPrivacy, setSelectedPrivacy] = useState<PrivacyChoice>(
    isCurrentlyPublic ? "public" : isCurrentlyMembers ? "people" : "private"
  );
  const [shareLink, setShareLink] = useState<string>(
    isCurrentlyPublic ? buildShareLink(chatSession.id) : ""
  );
  const [isLoading, setIsLoading] = useState(false);
  const [stagedUsers, setStagedUsers] = useState<MinimalUserSnapshot[]>([]);
  const [stagedGroups, setStagedGroups] = useState<MinimalUserGroupSnapshot[]>(
    []
  );
  const { data: users = [] } = useShareableUsers({ includeApiKeys: false });
  const { data: groups = [] } = useShareableGroups();
  const updateCurrentChatSessionSharedStatus = useChatSessionStore(
    (state) => state.updateCurrentChatSessionSharedStatus
  );
  const { refreshChatSessions } = useChatSessions();

  useEffect(() => {
    let cancelled = false;
    async function loadShares() {
      const response = await fetch(
        `/api/chat/chat-session/${chatSession.id}/shares`
      );
      if (!response.ok || cancelled) {
        return;
      }
      const payload = (await response.json()) as {
        shared_user_ids: string[];
        shared_group_ids: number[];
      };
      if (cancelled) {
        return;
      }
      setStagedUsers(
        users.filter((user) => payload.shared_user_ids.includes(user.id))
      );
      setStagedGroups(
        groups.filter((group) => payload.shared_group_ids.includes(group.id))
      );
    }
    void loadShares();
    return () => {
      cancelled = true;
    };
  }, [chatSession.id, users, groups]);

  const existingUserIds = useMemo(() => new Set<string>(), []);
  const existingGroupIds = useMemo(() => new Set<number>(), []);

  const wantsPublic = selectedPrivacy === "public";
  const wantsPeople = selectedPrivacy === "people";
  const isShared = shareLink && selectedPrivacy === "public";

  let submitButtonText: string;
  if (wantsPeople) {
    submitButtonText = "Share with people";
  } else if (isShared) {
    submitButtonText = t("copyLinkButton.label");
  } else if (
    (isCurrentlyPublic || isCurrentlyMembers) &&
    selectedPrivacy === "private"
  ) {
    submitButtonText = t("makePrivateButton.label");
  } else {
    submitButtonText = t("createLinkButton.label");
  }

  const submitDisabled =
    isLoading ||
    (selectedPrivacy === "private" &&
      !isCurrentlyPublic &&
      !isCurrentlyMembers) ||
    (wantsPeople && stagedUsers.length === 0 && stagedGroups.length === 0);

  async function handleSubmit() {
    setIsLoading(true);
    try {
      if (wantsPeople) {
        const success = await saveMemberShares(
          chatSession.id,
          stagedUsers.map((user) => user.id),
          stagedGroups.map((group) => group.id)
        );
        if (success) {
          updateCurrentChatSessionSharedStatus(ChatSessionSharedStatus.Shared);
          await refreshChatSessions();
          toast.success("Chat shared with selected people and groups.");
          onClose();
        } else {
          toast.error(t("genericErrorToast.message"));
        }
      } else if (wantsPublic && !isCurrentlyPublic && !shareLink) {
        const link = await generateShareLink(chatSession.id);
        if (link) {
          setShareLink(link);
          updateCurrentChatSessionSharedStatus(ChatSessionSharedStatus.Public);
          await refreshChatSessions();
          copyAll(link);
          toast.success(t("linkCopiedToast.message"));
        } else {
          toast.error(t("generateLinkErrorToast.message"));
        }
      } else if (!wantsPublic && (isCurrentlyPublic || isCurrentlyMembers)) {
        const success = await deleteShareLink(chatSession.id);
        if (success) {
          setShareLink("");
          updateCurrentChatSessionSharedStatus(ChatSessionSharedStatus.Private);
          await refreshChatSessions();
          toast.success(t("nowPrivateToast.message"));
          onClose();
        } else {
          toast.error(t("makePrivateErrorToast.message"));
        }
      } else if (wantsPublic && shareLink) {
        copyAll(shareLink);
        toast.success(t("linkCopiedToast.message"));
      } else {
        onClose();
      }
    } catch (e) {
      console.error(e);
      toast.error(t("genericErrorToast.message"));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <Modal open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <Modal.Content width={wantsPeople ? "md" : "sm"}>
        <Modal.Header
          icon={SvgShare}
          title={isShared ? t("header.sharedTitle") : t("header.title")}
          description={t("header.description")}
          onClose={onClose}
        />
        <Modal.Body twoTone>
          <Section
            justifyContent="start"
            alignItems="stretch"
            height="auto"
            gap={1}
          >
            <PrivacyOption
              icon={SvgLock}
              title={t("privateOption.title")}
              description={t("privateOption.description")}
              selected={selectedPrivacy === "private"}
              onClick={() => setSelectedPrivacy("private")}
              ariaLabel="share-modal-option-private"
            />
            <PrivacyOption
              icon={SvgUser}
              title="Specific people"
              description="Share this chat with selected users or groups."
              selected={selectedPrivacy === "people"}
              onClick={() => setSelectedPrivacy("people")}
              ariaLabel="share-modal-option-people"
            />
            <PrivacyOption
              icon={SvgUsers}
              title={t("organizationOption.title")}
              description={t("organizationOption.description")}
              selected={selectedPrivacy === "public"}
              onClick={() => setSelectedPrivacy("public")}
              ariaLabel="share-modal-option-public"
            />
          </Section>

          {wantsPeople && (
            <AddPeoplePicker
              existingGroupIds={existingGroupIds}
              existingUserIds={existingUserIds}
              groups={groups}
              users={users}
              stagedGroups={stagedGroups}
              stagedUsers={stagedUsers}
              stagedPermission="VIEWER"
              onAddGroup={(group) =>
                setStagedGroups((current) => [...current, group])
              }
              onAddUser={(user) =>
                setStagedUsers((current) => [...current, user])
              }
              onRemoveGroup={(groupId) =>
                setStagedGroups((current) =>
                  current.filter((group) => group.id !== groupId)
                )
              }
              onRemoveUser={(userId) =>
                setStagedUsers((current) =>
                  current.filter((user) => user.id !== userId)
                )
              }
              onStagedPermissionChange={() => undefined}
            />
          )}

          {isShared && (
            <InputTypeIn
              aria-label="share-modal-link-input"
              variant="readOnly"
              value={shareLink}
              rightChildren={
                <CopyButton
                  getCopyText={() => shareLink}
                  tooltip={t("linkInput.copyTooltip")}
                  size="sm"
                  aria-label="share-modal-copy-link"
                />
              }
            />
          )}
        </Modal.Body>
        <Modal.Footer>
          {!isShared && (
            <Button
              prominence="secondary"
              onClick={onClose}
              aria-label="share-modal-cancel"
            >
              {t("cancelButton.label")}
            </Button>
          )}
          <Button
            disabled={submitDisabled}
            onClick={handleSubmit}
            icon={isShared ? SvgLink : undefined}
            width={isShared ? "full" : undefined}
            aria-label="share-modal-submit"
          >
            {submitButtonText}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
