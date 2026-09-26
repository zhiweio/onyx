"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  InputTypeIn,
  MessageCard,
  Table,
  Tag,
  Text,
  Tooltip,
  createTableColumns,
} from "@opal/components";
import {
  ConfirmationModalLayout,
  IllustrationContent,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { localizeAndPrettify, timeAgo } from "@opal/time";
import {
  SvgEdit,
  SvgKey,
  SvgPlus,
  SvgSimpleLoader,
  SvgTerminal,
  SvgTrash,
} from "@opal/icons";
import { useEnvVars } from "@/hooks/useEnvVars";
import { useCraftProjects } from "@/lib/craft-projects/hooks";
import { deleteEnvVar } from "@/app/craft/v1/env-vars/api";
import type { EnvVarItem } from "@/app/craft/v1/env-vars/interfaces";
import EnvVarFormModal from "@/app/craft/v1/env-vars/EnvVarFormModal";

const tc = createTableColumns<EnvVarItem>();

const ENV_VARS_PAGE_SIZE = 10;

type PageTranslate = ReturnType<typeof useTranslations<"craft.envVars.page">>;

interface ColumnHandlers {
  onEdit: (item: EnvVarItem) => void;
  onDelete: (item: EnvVarItem) => void;
}

function buildColumns(handlers: ColumnHandlers, t: PageTranslate) {
  return [
    tc.qualifier({
      content: "icon",
      getContent: (row) => (row.is_secret ? SvgKey : SvgTerminal),
    }),
    tc.column("name", {
      header: t("table.columns.name"),
      weight: 24,
      cell: (value) => (
        <Text font="secondary-mono" color="text-05" className="break-all">
          {value}
        </Text>
      ),
    }),
    tc.column("value", {
      header: t("table.columns.value"),
      weight: 24,
      cell: (value, row) => {
        // Secrets are write-only — the API never returns their value.
        if (row.is_secret) {
          return (
            <Text font="secondary-mono" color="text-03" nowrap>
              ••••••••
            </Text>
          );
        }
        if (!value) {
          return (
            <Text font="main-ui-body" color="text-03">
              —
            </Text>
          );
        }
        return (
          <Tooltip tooltip={value} side="top">
            <Text
              font="secondary-mono"
              color="text-03"
              nowrap
              className="block max-w-full truncate"
            >
              {value}
            </Text>
          </Tooltip>
        );
      },
    }),
    tc.displayColumn({
      id: "type",
      header: t("table.columns.type"),
      width: { weight: 10, minWidth: 90 },
      cell: (row) =>
        row.is_secret ? (
          <Tag title={t("badges.secret")} color="amber" />
        ) : (
          <Tag title={t("badges.variable")} color="blue" />
        ),
    }),
    tc.displayColumn({
      id: "scope",
      header: t("table.columns.scope"),
      width: { weight: 16, minWidth: 120 },
      cell: (row) =>
        row.scope === "USER" ? (
          <Tag title={t("groups.personal")} color="gray" />
        ) : (
          <Tag
            title={row.project_name ?? t("groups.unnamedProject")}
            color="blue"
            truncate
          />
        ),
    }),
    tc.column("updated_at", {
      header: t("table.columns.updated"),
      weight: 14,
      cell: (value) => (
        <Tooltip tooltip={localizeAndPrettify(value)} side="top">
          <Text font="main-ui-body" color="text-03" nowrap>
            {timeAgo(value) ?? "—"}
          </Text>
        </Tooltip>
      ),
    }),
    tc.actions({
      showColumnVisibility: false,
      showSorting: false,
      cell: (row) => <EnvVarRowActions item={row} handlers={handlers} />,
    }),
  ];
}

/**
 * Management page for env vars / secrets: the caller's personal rows plus
 * every readable project's rows in one searchable table. Secrets are
 * write-only — only their masked value and update time are shown. Rows the
 * caller cannot manage (project scope without write access) render read-only.
 */
export default function EnvVarsPage() {
  const t = useTranslations("craft.envVars.page");
  const { data: envVars, error, isLoading, refresh } = useEnvVars();
  const { data: projects } = useCraftProjects();
  const [search, setSearch] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<EnvVarItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EnvVarItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const filteredVars = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return envVars;
    return envVars.filter(
      (item) =>
        item.name.toLowerCase().includes(query) ||
        (item.project_name ?? "").toLowerCase().includes(query) ||
        (!item.is_secret && (item.value ?? "").toLowerCase().includes(query))
    );
  }, [envVars, search]);

  const openEdit = useCallback((item: EnvVarItem) => {
    setEditing(item);
    setFormOpen(true);
  }, []);

  const requestDelete = useCallback(
    (item: EnvVarItem) => setDeleteTarget(item),
    []
  );

  const columns = useMemo(
    () => buildColumns({ onEdit: openEdit, onDelete: requestDelete }, t),
    [openEdit, requestDelete, t]
  );

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
    <SettingsLayouts.Root width="lg" data-testid="EnvVarsPage/container">
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
        {isLoading && (
          <div className="flex justify-center py-12">
            <SvgSimpleLoader className="h-6 w-6" />
          </div>
        )}

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

        {!isLoading && !error && envVars.length > 0 && (
          <div className="flex flex-col gap-3">
            <div className="px-2">
              <InputTypeIn
                variant="internal"
                searchIcon
                placeholder={t("list.search.placeholder")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <Table
              data={filteredVars}
              columns={columns}
              getRowId={(row) => row.id}
              pageSize={
                filteredVars.length > 0
                  ? Math.min(filteredVars.length, ENV_VARS_PAGE_SIZE)
                  : 1
              }
              initialSorting={[{ id: "name", desc: false }]}
              emptyState={
                <div className="flex justify-center py-10">
                  <Text font="main-ui-body" color="text-03">
                    {t("list.noMatches")}
                  </Text>
                </div>
              }
            />
          </div>
        )}
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

interface EnvVarRowActionsProps {
  item: EnvVarItem;
  handlers: ColumnHandlers;
}

function EnvVarRowActions({ item, handlers }: EnvVarRowActionsProps) {
  const t = useTranslations("craft.envVars.page");
  if (!item.manageable) return null;
  return (
    <div className="flex items-center gap-0.5">
      <Tooltip tooltip={t("row.editLabel", { name: item.name })} side="top">
        <Button
          icon={SvgEdit}
          prominence="tertiary"
          size="sm"
          onClick={() => handlers.onEdit(item)}
          aria-label={t("row.editLabel", { name: item.name })}
          data-testid={`env-var-edit-${item.id}`}
        />
      </Tooltip>
      <Tooltip tooltip={t("row.deleteLabel", { name: item.name })} side="top">
        <Button
          icon={SvgTrash}
          variant="danger"
          prominence="tertiary"
          size="sm"
          onClick={() => handlers.onDelete(item)}
          aria-label={t("row.deleteLabel", { name: item.name })}
          data-testid={`env-var-delete-${item.id}`}
        />
      </Tooltip>
    </div>
  );
}
