"use client";

import { useMemo, useState } from "react";
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
import { TruncatedTextCell } from "@/components/admin/TableCells";
import {
  deleteAgentModelOverlay,
  fetchAgentModels,
  verifyAgentModelOverlay,
  type AgentModelView,
} from "./api";
import OverlayFormModal from "./OverlayFormModal";

const PAGE_SIZE = 10;

const tc = createTableColumns<AgentModelView>();

export default function AgentModelsPage() {
  const t = useTranslations("admin.agentModels");
  const adminRouteTitle = useAdminRouteTitle();
  const route = ADMIN_ROUTES.AGENT_MODELS;
  const [searchTerm, setSearchTerm] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AgentModelView | null>(
    null
  );

  const { data, isLoading, error, mutate } = useSWR(
    SWR_KEYS.adminAgentModels,
    fetchAgentModels
  );
  const models = useMemo(() => data?.models ?? [], [data]);
  const catalog = useMemo(
    () => models.filter((model) => !model.overlay),
    [models]
  );

  const verify = async (overlayId: number) => {
    setBusyId(overlayId);
    try {
      const row = await verifyAgentModelOverlay(overlayId);
      if (row.verified_at) {
        toast.success(t("verified"));
      } else {
        toast.error(`${t("verifyFailed")}: ${row.verify_error ?? ""}`);
      }
      await mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (overlayId: number) => {
    setBusyId(overlayId);
    try {
      await deleteAgentModelOverlay(overlayId);
      toast.success(t("deleted"));
      setPendingDelete(null);
      await mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  const columns = useMemo(
    () => [
      tc.column("display_name", {
        header: t("col.model"),
        weight: 24,
        enableSorting: false,
        cell: (value, row) => (
          <div className="flex min-w-0 items-center gap-1">
            <TruncatedTextCell value={value} empty="" />
            {row.is_default ? <Tag title={t("default")} color="blue" /> : null}
          </div>
        ),
      }),
      tc.column("provider", {
        header: t("col.provider"),
        weight: 12,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" />,
      }),
      tc.column("context_window", {
        header: t("col.context"),
        weight: 12,
        enableSorting: false,
        cell: (value) => (
          <Text font="secondary-mono" color="text-04" nowrap>
            {value.toLocaleString()}
          </Text>
        ),
      }),
      tc.column("runtimes", {
        header: t("col.runtimes"),
        weight: 20,
        enableSorting: false,
        cell: (value) => (
          <div className="flex flex-wrap items-center gap-1">
            {value.map((runtime) => (
              <Tag key={runtime} title={runtime} />
            ))}
          </div>
        ),
      }),
      tc.column("overlay", {
        header: t("col.source"),
        weight: 20,
        enableSorting: false,
        cell: (value) => {
          if (!value) {
            return <Tag title={t("sourceCatalog")} color="gray" />;
          }
          if (value.verified_at) {
            return (
              <Tag
                title={t("sourceOverlay")}
                value={t("verified")}
                color="green"
                tooltip={new Date(value.verified_at).toLocaleString()}
              />
            );
          }
          if (value.verify_error) {
            return (
              <Tag
                title={t("verifyError")}
                color="red"
                tooltip={value.verify_error}
              />
            );
          }
          return (
            <Tag
              title={t("sourceOverlay")}
              value={t("notVerified")}
              color="amber"
            />
          );
        },
      }),
      tc.actions({
        showColumnVisibility: false,
        showSorting: false,
        cell: (row) =>
          row.overlay ? (
            <div className="flex gap-2">
              <Button
                prominence="internal"
                disabled={busyId !== null}
                onClick={() => void verify(row.overlay!.id)}
              >
                {t("verify")}
              </Button>
              <Button
                prominence="internal"
                disabled={busyId !== null}
                onClick={() => setPendingDelete(row)}
              >
                {t("delete")}
              </Button>
            </div>
          ) : null,
      }),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, busyId]
  );

  return (
    <SettingsLayouts.Root width="lg" data-testid="agent-models-page">
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        description={t("subtitle")}
        divider
        rightChildren={
          <Button
            icon={ADMIN_ROUTES.AGENT_MODELS.icon}
            onClick={() => setFormOpen(true)}
            data-testid="agent-models-add"
          >
            {t("addOverlay")}
          </Button>
        }
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-3">
          <div className="max-w-sm">
            <InputTypeIn
              searchIcon
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder={t("searchPlaceholder")}
              aria-label={t("searchPlaceholder")}
              data-testid="agent-models-search"
            />
          </div>
          <Table
            data={models}
            columns={columns}
            getRowId={(row) => row.model_id}
            pageSize={PAGE_SIZE}
            variant="cards"
            searchTerm={searchTerm}
            footer={{ units: t("footerUnits") }}
            emptyState={
              <IllustrationContent
                illustration={SvgNoResult}
                title={
                  isLoading
                    ? t("loading")
                    : error
                      ? t("loadFailed")
                      : t("empty")
                }
              />
            }
          />
        </div>
      </SettingsLayouts.Body>

      <OverlayFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSaved={mutate}
        catalog={catalog}
      />

      {pendingDelete?.overlay ? (
        <ConfirmationModalLayout
          icon={route.icon}
          title={t("deleteTitle")}
          onClose={() => setPendingDelete(null)}
          submit={
            <>
              <Button
                prominence="secondary"
                disabled={busyId !== null}
                onClick={() => setPendingDelete(null)}
              >
                {t("cancel")}
              </Button>
              <Button
                disabled={busyId !== null}
                data-testid="agent-model-confirm-delete"
                onClick={() => void remove(pendingDelete.overlay!.id)}
              >
                {t("delete")}
              </Button>
            </>
          }
        >
          <Text as="p" color="text-03">
            {t("deleteBody", { name: pendingDelete.display_name })}
          </Text>
        </ConfirmationModalLayout>
      ) : null}
    </SettingsLayouts.Root>
  );
}
