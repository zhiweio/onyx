"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import {
  Button,
  InputTypeIn,
  Table,
  Tag,
  Text,
  createTableColumns,
} from "@opal/components";
import {
  ConfirmationModalLayout,
  IllustrationContent,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";
import { TruncatedTextCell } from "@/components/admin/TableCells";
import { useServerPaginatedTable } from "@/hooks/useServerPaginatedTable";
import AdminListHeader from "@/sections/admin/AdminListHeader";
import {
  createStandardAnswerCategory,
  deleteStandardAnswer,
  fetchStandardAnswerCategories,
  fetchStandardAnswers,
  updateStandardAnswer,
  type StandardAnswerRow,
} from "./api";
import AnswerFormModal from "./AnswerFormModal";

const PAGE_SIZE = 20;

const tc = createTableColumns<StandardAnswerRow>();

export default function StandardAnswerPage() {
  const t = useTranslations("admin.standardAnswers");
  const adminRouteTitle = useAdminRouteTitle();
  const route = ADMIN_ROUTES.STANDARD_ANSWERS;
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<StandardAnswerRow | null>(null);
  const [pendingDelete, setPendingDelete] = useState<StandardAnswerRow | null>(
    null
  );
  const [pendingToggle, setPendingToggle] = useState<StandardAnswerRow | null>(
    null
  );
  const [busy, setBusy] = useState(false);
  const [newCategory, setNewCategory] = useState("");

  const { data: categories = [], mutate: mutateCategories } = useSWR(
    SWR_KEYS.adminStandardAnswerCategories,
    () => fetchStandardAnswerCategories()
  );

  const {
    searchInputProps,
    searchTerm,
    setSearchInput,
    rows,
    total,
    isLoading,
    error,
    reload,
    serverSide,
  } = useServerPaginatedTable<StandardAnswerRow>({
    requestKey: `answers\0${categoryId ?? "all"}`,
    pageSize: PAGE_SIZE,
    loader: ({ offset, limit, q }) =>
      fetchStandardAnswers({ q, category_id: categoryId, offset, limit }),
  });

  useEffect(() => {
    if (error) {
      toast.error(errorMessage(error, t("loadFailed")));
    }
  }, [error, t]);

  const categoryNameById = useMemo(
    () => new Map(categories.map((category) => [category.id, category.name])),
    [categories]
  );

  const addCategory = async () => {
    const name = newCategory.trim();
    if (!name) return;
    setBusy(true);
    try {
      await createStandardAnswerCategory(name);
      toast.success(t("categoryCreated"));
      setNewCategory("");
      await mutateCategories();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (row: StandardAnswerRow) => {
    setBusy(true);
    try {
      await updateStandardAnswer(row.id, { active: !row.active });
      setPendingToggle(null);
      await reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: StandardAnswerRow) => {
    setBusy(true);
    try {
      await deleteStandardAnswer(row.id);
      toast.success(t("deleted"));
      setPendingDelete(null);
      await reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const columns = useMemo(
    () => [
      tc.column("keyword", {
        header: t("col.keyword"),
        weight: 22,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" mono />,
      }),
      tc.column("answer", {
        header: t("col.answer"),
        weight: 38,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" />,
      }),
      tc.column("category_ids", {
        header: t("col.categories"),
        weight: 16,
        enableSorting: false,
        cell: (value) => (
          <div className="flex flex-wrap items-center gap-1">
            {value.map((id) => (
              <Tag key={id} title={categoryNameById.get(id) ?? String(id)} />
            ))}
          </div>
        ),
      }),
      tc.column("active", {
        header: t("col.status"),
        weight: 10,
        enableSorting: false,
        cell: (value) =>
          value ? (
            <Tag title={t("active")} color="green" />
          ) : (
            <Tag title={t("inactive")} color="gray" />
          ),
      }),
      tc.actions({
        showColumnVisibility: false,
        showSorting: false,
        cell: (row) => (
          <div className="flex gap-2">
            <Button
              prominence="internal"
              disabled={busy}
              onClick={() => {
                setEditing(row);
                setFormOpen(true);
              }}
            >
              {t("edit")}
            </Button>
            <Button
              prominence="internal"
              disabled={busy}
              onClick={() => setPendingToggle(row)}
            >
              {row.active ? t("disable") : t("enable")}
            </Button>
            <Button
              prominence="internal"
              disabled={busy}
              onClick={() => setPendingDelete(row)}
            >
              {t("delete")}
            </Button>
          </div>
        ),
      }),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, busy, categoryNameById]
  );

  return (
    <SettingsLayouts.Root width="lg" data-testid="standard-answers-page">
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        description={t("subtitle")}
        divider
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-4">
          <AdminListHeader
            hasItems={total > 0 || isLoading}
            searchQuery={searchInputProps.value}
            onSearchQueryChange={setSearchInput}
            placeholder={t("searchPlaceholder")}
            emptyStateText={t("empty")}
            onAction={() => {
              setEditing(null);
              setFormOpen(true);
            }}
            actionLabel={t("addAnswer")}
          />

          <div
            className="flex flex-wrap items-center gap-2"
            data-testid="standard-answer-category-filters"
          >
            <Button
              size="sm"
              prominence={categoryId === null ? "primary" : "secondary"}
              onClick={() => setCategoryId(null)}
            >
              {t("allCategories")}
            </Button>
            {categories.map((category) => (
              <Button
                key={category.id}
                size="sm"
                prominence={
                  categoryId === category.id ? "primary" : "secondary"
                }
                onClick={() =>
                  setCategoryId(category.id === categoryId ? null : category.id)
                }
              >
                {category.name}
              </Button>
            ))}
            <div className="ms-2 flex items-center gap-1">
              <div className="w-44">
                <InputTypeIn
                  value={newCategory}
                  onChange={(event) => setNewCategory(event.target.value)}
                  placeholder={t("newCategory")}
                  aria-label={t("newCategory")}
                  data-testid="standard-answer-new-category"
                />
              </div>
              <Button
                size="sm"
                prominence="tertiary"
                disabled={busy || !newCategory.trim()}
                onClick={() => void addCategory()}
              >
                {t("addCategory")}
              </Button>
            </div>
          </div>

          <Table
            data={rows}
            columns={columns}
            getRowId={(row) => String(row.id)}
            pageSize={PAGE_SIZE}
            variant="cards"
            searchTerm={searchTerm}
            footer={{ units: t("footerUnits") }}
            emptyState={
              <IllustrationContent
                illustration={SvgNoResult}
                title={isLoading ? t("loading") : t("emptyTable")}
              />
            }
            serverSide={serverSide}
          />
        </div>
      </SettingsLayouts.Body>

      <AnswerFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSaved={reload}
        categories={categories}
        initial={editing}
      />

      {pendingToggle ? (
        <ConfirmationModalLayout
          icon={route.icon}
          title={
            pendingToggle.active
              ? t("confirmDisableTitle")
              : t("confirmEnableTitle")
          }
          onClose={() => setPendingToggle(null)}
          submit={
            <>
              <Button
                prominence="secondary"
                disabled={busy}
                onClick={() => setPendingToggle(null)}
              >
                {t("cancel")}
              </Button>
              <Button
                disabled={busy}
                data-testid="standard-answer-confirm-toggle"
                onClick={() => void toggleActive(pendingToggle)}
              >
                {pendingToggle.active ? t("disable") : t("enable")}
              </Button>
            </>
          }
        >
          <Text as="p" color="text-03">
            {pendingToggle.active
              ? t("confirmDisableBody", { keyword: pendingToggle.keyword })
              : t("confirmEnableBody", { keyword: pendingToggle.keyword })}
          </Text>
        </ConfirmationModalLayout>
      ) : null}

      {pendingDelete ? (
        <ConfirmationModalLayout
          icon={route.icon}
          title={t("confirmDeleteTitle")}
          onClose={() => setPendingDelete(null)}
          submit={
            <>
              <Button
                prominence="secondary"
                disabled={busy}
                onClick={() => setPendingDelete(null)}
              >
                {t("cancel")}
              </Button>
              <Button
                disabled={busy}
                data-testid="standard-answer-confirm-delete"
                onClick={() => void remove(pendingDelete)}
              >
                {t("delete")}
              </Button>
            </>
          }
        >
          <Text as="p" color="text-03">
            {t("confirmDeleteBody", { keyword: pendingDelete.keyword })}
          </Text>
        </ConfirmationModalLayout>
      ) : null}
    </SettingsLayouts.Root>
  );
}
