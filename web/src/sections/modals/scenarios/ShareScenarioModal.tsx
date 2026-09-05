"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Modal, Switch, Text } from "@opal/components";
import { toast } from "@opal/layouts";
import { SvgShare } from "@opal/icons";
import useShareableGroups, {
  type MinimalUserGroupSnapshot,
} from "@/hooks/useShareableGroups";
import useShareableUsers from "@/hooks/useShareableUsers";
import { shareScenario } from "@/lib/scenarios/api";
import type { Scenario } from "@/lib/scenarios/types";
import { AddPeoplePicker } from "@/sections/modals/AddPeoplePicker";
import type { MinimalUserSnapshot } from "@/lib/types";

interface ShareScenarioModalProps {
  scenario: Scenario | null;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export default function ShareScenarioModal({
  scenario,
  open,
  onClose,
  onSaved,
}: ShareScenarioModalProps) {
  const t = useTranslations("craft.scenarios.share");
  const toastT = useTranslations("craft.scenarios.toasts");
  const { data: users } = useShareableUsers({ includeApiKeys: true });
  const { data: groups } = useShareableGroups();

  const [userIds, setUserIds] = useState<string[]>([]);
  const [groupIds, setGroupIds] = useState<number[]>([]);
  const [isPublic, setIsPublic] = useState(false);
  const [stagedUsers, setStagedUsers] = useState<MinimalUserSnapshot[]>([]);
  const [stagedGroups, setStagedGroups] = useState<MinimalUserGroupSnapshot[]>(
    []
  );
  const [saving, setSaving] = useState(false);
  const [hydratedId, setHydratedId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setHydratedId(null);
      return;
    }
    if (!scenario || scenario.id === hydratedId) return;
    setUserIds(scenario.shared_user_ids);
    setGroupIds(scenario.shared_group_ids);
    setIsPublic(scenario.public_permission !== null);
    setStagedUsers([]);
    setStagedGroups([]);
    setHydratedId(scenario.id);
  }, [open, scenario, hydratedId]);

  const existingUserIds = useMemo(() => new Set(userIds), [userIds]);
  const existingGroupIds = useMemo(() => new Set(groupIds), [groupIds]);

  const selectedUsers = useMemo(
    () => (users ?? []).filter((user) => userIds.includes(user.id)),
    [users, userIds]
  );
  const selectedGroups = useMemo(
    () => (groups ?? []).filter((group) => groupIds.includes(group.id)),
    [groups, groupIds]
  );

  async function handleSave() {
    if (!scenario) return;
    setSaving(true);
    try {
      await shareScenario(scenario.id, {
        user_ids: Array.from(
          new Set([...userIds, ...stagedUsers.map((user) => user.id)])
        ),
        group_ids: Array.from(
          new Set([...groupIds, ...stagedGroups.map((group) => group.id)])
        ),
        public_permission: isPublic ? "VIEWER" : null,
      });
      toast.success(toastT("shared.message"));
      onSaved();
      onClose();
    } catch (error) {
      console.error(error);
      toast.error(toastT("shareFailed.message"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onOpenChange={(next) => !next && onClose()}>
      <Modal.Content width="md">
        <Modal.Header
          icon={SvgShare}
          title={t("title.text")}
          description={t("description.text")}
          onClose={onClose}
        />
        <Modal.Body>
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <Text>{isPublic ? t("org.on.label") : t("org.off.label")}</Text>
            <Switch
              checked={isPublic}
              onCheckedChange={setIsPublic}
              aria-label={t("org.on.label")}
            />
          </div>
          <AddPeoplePicker
            existingGroupIds={existingGroupIds}
            existingUserIds={existingUserIds}
            groups={groups ?? []}
            users={users ?? []}
            stagedGroups={stagedGroups}
            stagedUsers={stagedUsers}
            stagedPermission="VIEWER"
            onStagedPermissionChange={() => undefined}
            onAddUser={(user) => {
              setStagedUsers((current) => [...current, user]);
            }}
            onAddGroup={(group) => {
              setStagedGroups((current) => [...current, group]);
            }}
            onRemoveUser={(userId) => {
              setStagedUsers((current) =>
                current.filter((user) => user.id !== userId)
              );
              setUserIds((current) => current.filter((id) => id !== userId));
            }}
            onRemoveGroup={(groupId) => {
              setStagedGroups((current) =>
                current.filter((group) => group.id !== groupId)
              );
              setGroupIds((current) => current.filter((id) => id !== groupId));
            }}
          />
          {(selectedUsers.length > 0 || selectedGroups.length > 0) && (
            <Text color="text-02">
              {[
                ...selectedUsers.map((user) => user.email),
                ...selectedGroups.map((group) => group.name),
              ].join(", ")}
            </Text>
          )}
        </div>
        </Modal.Body>
        <Modal.Footer>
          <Button prominence="secondary" onClick={onClose} disabled={saving}>
            {t("cancel.label")}
          </Button>
          <Button onClick={() => void handleSave()} disabled={saving}>
            {saving ? t("saving.label") : t("save.label")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
