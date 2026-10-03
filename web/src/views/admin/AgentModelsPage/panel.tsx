"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import {
  InputTypeIn,
  Table,
  Tag,
  Text,
  createTableColumns,
} from "@opal/components";
import { IllustrationContent } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { SWR_KEYS } from "@/lib/swr-keys";
import { TruncatedTextCell } from "@/components/admin/TableCells";
import { fetchAgentModels, type AgentModelView } from "./api";

const PAGE_SIZE = 10;

const tc = createTableColumns<AgentModelView>();

/**
 * Read-only sandbox view over the configured LLM providers (the "Model
 * Providers" tab) — the single source of truth. Adding models happens in
 * the provider modals; the sandbox default follows the Craft preference
 * default. Lives as a tab on the Language Models page — the agent-models
 * route redirects there.
 */
export default function AgentModelsPanel() {
  const t = useTranslations("admin.agentModels");
  const [searchTerm, setSearchTerm] = useState("");

  const { data, isLoading, error } = useSWR(
    SWR_KEYS.adminAgentModels,
    fetchAgentModels
  );
  const models = useMemo(() => data?.models ?? [], [data]);

  const columns = useMemo(
    () => [
      tc.column("display_name", {
        header: t("col.model"),
        weight: 28,
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
        weight: 16,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" />,
      }),
      tc.column("context_window", {
        header: t("col.context"),
        weight: 16,
        enableSorting: false,
        cell: (value) => (
          <Text font="secondary-mono" color="text-04" nowrap>
            {value == null ? "—" : value.toLocaleString()}
          </Text>
        ),
      }),
      tc.column("runtimes", {
        header: t("col.runtimes"),
        weight: 20,
        enableSorting: false,
        cell: (value) => (
          <div className="flex flex-wrap items-center gap-1">
            {value.map((runtime: string) => (
              <Tag key={runtime} title={runtime} />
            ))}
          </div>
        ),
      }),
    ],
    [t]
  );

  return (
    <div className="flex flex-col gap-3" data-testid="agent-models-page">
      <div className="flex flex-col gap-1">
        <Text as="p" color="text-03">
          {t("subtitle")}
        </Text>
        <Text as="p" color="text-03">
          {t("hintProviders")}
        </Text>
        <Text as="p" color="text-03">
          {t("hintDefault")}
        </Text>
      </div>
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
              isLoading ? t("loading") : error ? t("loadFailed") : t("empty")
            }
          />
        }
      />
    </div>
  );
}
