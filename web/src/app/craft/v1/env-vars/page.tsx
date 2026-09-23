"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Card, MessageCard, Tag, Text } from "@opal/components";
import {
  ConfirmationModalLayout,
  IllustrationContent,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import {
  SvgEdit,
  SvgKey,
  SvgPlus,
  SvgSimpleLoader,
  SvgTrash,
} from "@opal/icons";
import { useEnvVars } from "@/hooks/useEnvVars";
import { useCraftProjects } from "@/lib/craft-projects/hooks";
import { deleteEnvVar } from "@/app/craft/v1/env-vars/api";
import type { EnvVarItem } from "@/app/craft/v1/env-vars/interfaces";
import EnvVarFormModal from "@/app/craft/v1/env-vars/EnvVarFormModal";

interface EnvVarGroup {
  key: string;
  title: string;
  items: EnvVarItem[];
}

/**
 * Management page for env vars / secrets: the caller's personal rows plus
 * every readable project's rows, grouped by scope. Secrets are write-only —
 * only their name and update time are shown. Rows the caller cannot manage
 * (project scope without write access) render read-only.
 */
export default function EnvVarsPage() {
  const t = useTranslations("craft.envVars.page");
  const { data: envVars, error, isLoading, refresh } = useEnvVars();
  const { data: projects } = useCraftProjects();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<EnvVarItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EnvVarItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const groups = useMemo<EnvVarGroup[]>(() => {
    const personal = envVars.filter((item) => item.scope === "USER");
    const result: EnvVarGroup[] = [
      { key: "user", title: t("groups.personal"), items: personal },
    ];
    const byProject = new Map<string, EnvVarItem[]>();
    for (const item of envVars) {
      if (item.scope !== "PROJECT") continue;
      const key = item.project_id ?? "";
      const bucket = byProject.get(key);
      if (bucket) bucket.push(item);
      else byProject.set(key, [item]);
    }
    for (const [projectId, items] of byProject) {
      result.push({
        key: projectId,
        title: items[0]?.project_name ?? t("groups.unnamedProject"),
        items,
      });
    }
    return result.filter((group) => group.items.length > 0);
  }, [envVars, t]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteEnvVar(deleteTarget.id);
      setDeleteTarget(null);
      await refresh();
      toast.success(t("toasts.deleted"));
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t("toasts.deleteFailed")
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <SettingsLayouts.Root data-testid="EnvVarsPage/container">
      <SettingsLayouts.Header
        icon={SvgKey}
        title={t("title")}
        description={t("description")}
        divider
        rightChildren={
          <Button
            icon={SvgPlus}
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            {t("createButton")}
          </Button>
        }
      />

      <SettingsLayouts.Body>
        {isLoading && <SvgSimpleLoader />}

        {error && !isLoading && (
          <MessageCard
            variant="error"
            title={t("error.title")}
            description={t("error.description")}
          />
        )}

        {!isLoading && !error && envVars.length === 0 && (
          <IllustrationContent
            illustration={SvgNoResult}
            title={t("empty.title")}
            description={t("empty.description")}
          />
        )}

        {!isLoading &&
          !error &&
          groups.map((group) => (
            <section
              key={group.key}
              className="flex flex-col gap-2"
              aria-label={group.title}
            >
              <Text as="h3" font="main-ui-action" color="text-03">
                {group.title}
              </Text>
              <div className="flex flex-col gap-2">
                {group.items.map((item) => (
                  <EnvVarRow
                    key={item.id}
                    item={item}
                    onEdit={() => {
                      setEditing(item);
                      setFormOpen(true);
                    }}
                    onDelete={() => setDeleteTarget(item)}
                  />
                ))}
              </div>
            </section>
          ))}
      </SettingsLayouts.Body>

      {formOpen && (
        <EnvVarFormModal
          open={formOpen}
          onClose={() => setFormOpen(false)}
          onSaved={refresh}
          initial={editing}
          projects={projects}
        />
      )}

      {deleteTarget && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("delete.title", { name: deleteTarget.name })}
          onClose={deleting ? undefined : () => setDeleteTarget(null)}
          submit={
            <Button
              variant="danger"
              disabled={deleting}
              onClick={() => void handleDelete()}
              data-testid="env-var-delete-confirm"
            >
              {t("delete.confirmButton")}
            </Button>
          }
        >
          <Text font="secondary-body">{t("delete.description")}</Text>
        </ConfirmationModalLayout>
      )}
    </SettingsLayouts.Root>
  );
}

interface EnvVarRowProps {
  item: EnvVarItem;
  onEdit: () => void;
  onDelete: () => void;
}

function EnvVarRow({ item, onEdit, onDelete }: EnvVarRowProps) {
  const t = useTranslations("craft.envVars.page");
  return (
    <Card background="light" border="solid" rounding={4}>
      <div className="flex w-full items-center gap-3">
        <div className="flex-1 flex flex-col gap-1 min-w-0">
          <div className="flex items-center gap-2">
            <Text font="main-ui-action" className="break-all">
              {item.name}
            </Text>
            {item.is_secret ? (
              <Tag title={t("badges.secret")} />
            ) : (
              <Tag title={t("badges.variable")} />
            )}
          </div>
          <Text font="secondary-body" color="text-03">
            {item.is_secret
              ? t("row.secretSetAt", {
                  date: new Date(item.updated_at).toLocaleString(),
                })
              : (item.value ?? "")}
          </Text>
        </div>
        {item.manageable && (
          <div className="flex gap-1">
            <Button
              icon={SvgEdit}
              variant="default"
              prominence="tertiary"
              onClick={onEdit}
              aria-label={t("row.editLabel", { name: item.name })}
              data-testid={`env-var-edit-${item.id}`}
            />
            <Button
              icon={SvgTrash}
              variant="default"
              prominence="tertiary"
              onClick={onDelete}
              aria-label={t("row.deleteLabel", { name: item.name })}
              data-testid={`env-var-delete-${item.id}`}
            />
          </div>
        )}
      </div>
    </Card>
  );
}
