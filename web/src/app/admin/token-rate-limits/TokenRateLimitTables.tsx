"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { deleteTokenRateLimit, updateTokenRateLimit } from "./lib";
import { IllustrationContent, PageLoader, toast } from "@opal/layouts";
import { TokenRateLimitDisplay } from "./types";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR, { mutate } from "swr";
import {
  Button,
  InputTypeIn,
  Switch,
  Table,
  Tag,
  Text,
  createTableColumns,
} from "@opal/components";
import SvgNoResult from "@opal/illustrations/no-result";
import { SvgTrash } from "@opal/icons";
import { formatCurrencyFromCents, formatTokenCount } from "@/lib/format";

const HOURS_PER_DAY = 24;
const PAGE_SIZE = 10;

interface TokenRateLimitRow extends TokenRateLimitDisplay {
  budget_label: string;
  cadence_label: string;
  row_label: string;
}

function buildRow(
  limit: TokenRateLimitDisplay,
  t: ReturnType<typeof useTranslations<"admin.tokenRateLimits">>,
  locale: string
): TokenRateLimitRow {
  const cost =
    limit.cost_budget_cents != null
      ? formatCurrencyFromCents(limit.cost_budget_cents, locale)
      : null;
  const tokens =
    limit.token_budget != null
      ? formatTokenCount(limit.token_budget * 1000, locale)
      : null;

  const budget =
    cost !== null && tokens !== null
      ? t("limits.budget.both", { cost, tokens })
      : cost !== null
        ? t("limits.budget.cost", { cost })
        : tokens !== null
          ? t("limits.budget.tokens", { tokens })
          : t("limits.budget.none");
  const cadence = t("limits.cadence.label", {
    days: limit.period_hours / HOURS_PER_DAY,
  });
  const limitLabel = t("limits.row.label", { budget, cadence });

  return {
    ...limit,
    budget_label: budget,
    cadence_label: cadence,
    row_label: limitLabel,
  };
}

type TokenRateLimitTableArgs = {
  tokenRateLimits: TokenRateLimitDisplay[];
  description?: string;
  fetchUrl: string;
  hideHeading?: boolean;
  isAdmin: boolean;
};

const tc = createTableColumns<TokenRateLimitRow>();

export const TokenRateLimitTable = ({
  tokenRateLimits,
  description,
  fetchUrl,
  hideHeading,
  isAdmin,
}: TokenRateLimitTableArgs) => {
  const t = useTranslations("admin.tokenRateLimits");
  const locale = useLocale();
  const [searchTerm, setSearchTerm] = useState("");

  const rows = useMemo(
    () => tokenRateLimits.map((limit) => buildRow(limit, t, locale)),
    [tokenRateLimits, t, locale]
  );

  const handleEnabledChange = async (id: number) => {
    const tokenRateLimit = tokenRateLimits.find(
      (tokenRateLimit) => tokenRateLimit.token_id === id
    );

    if (!tokenRateLimit) {
      return;
    }

    try {
      await updateTokenRateLimit(id, {
        token_budget: tokenRateLimit.token_budget,
        period_hours: tokenRateLimit.period_hours,
        cost_budget_cents: tokenRateLimit.cost_budget_cents,
        enabled: !tokenRateLimit.enabled,
      });
      await mutate(fetchUrl);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("limits.updateFailed.error")
      );
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteTokenRateLimit(id);
      await mutate(fetchUrl);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("limits.deleteFailed.error")
      );
    }
  };

  const columns = useMemo(
    () => [
      tc.column("budget_label", {
        header: t("limits.col.budget"),
        weight: 30,
        enableSorting: false,
        cell: (value) => (
          <Text font="main-ui-body" color="text-04" nowrap>
            {value}
          </Text>
        ),
      }),
      tc.column("cadence_label", {
        header: t("limits.col.cadence"),
        weight: 26,
        enableSorting: false,
        cell: (value) => (
          <Text font="secondary-body" color="text-03">
            {value}
          </Text>
        ),
      }),
      tc.column("group_name", {
        header: t("limits.col.target"),
        weight: 18,
        enableSorting: false,
        cell: (value) => (value ? <Tag title={value} truncate /> : null),
      }),
      tc.column("enabled", {
        header: t("limits.col.enabled"),
        weight: 10,
        enableSorting: false,
        cell: (value, row) => (
          <Switch
            checked={value}
            disabled={!isAdmin}
            onCheckedChange={() => handleEnabledChange(row.token_id)}
            aria-label={
              row.enabled
                ? t("limits.row.disable.ariaLabel", { label: row.row_label })
                : t("limits.row.enable.ariaLabel", { label: row.row_label })
            }
          />
        ),
      }),
      tc.actions({
        showColumnVisibility: false,
        showSorting: false,
        cell: (row) =>
          isAdmin ? (
            <Button
              variant="danger"
              prominence="tertiary"
              icon={SvgTrash}
              size="sm"
              tooltip={t("limits.row.delete.tooltip")}
              aria-label={t("limits.row.delete.ariaLabel", {
                label: row.row_label,
              })}
              onClick={() => handleDelete(row.token_id)}
            />
          ) : null,
      }),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, isAdmin, tokenRateLimits, fetchUrl]
  );

  return (
    <div className="flex flex-col gap-3">
      {!hideHeading && description && (
        <Text font="secondary-body" color="text-03" as="p">
          {description}
        </Text>
      )}
      <div className="max-w-sm">
        <InputTypeIn
          searchIcon
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          placeholder={t("limits.searchPlaceholder")}
          aria-label={t("limits.searchPlaceholder")}
          data-testid="token-rate-limits-search"
        />
      </div>
      <Table
        data={rows}
        columns={columns}
        getRowId={(row) => String(row.token_id)}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={searchTerm}
        footer={{ units: t("limits.footerUnits") }}
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={t("limits.empty.message")}
          />
        }
      />
    </div>
  );
};

export const GenericTokenRateLimitTable = ({
  fetchUrl,
  description,
  hideHeading,
  responseMapper,
  isAdmin = true,
}: {
  fetchUrl: string;
  description?: string;
  hideHeading?: boolean;
  responseMapper?: (data: any) => TokenRateLimitDisplay[];
  isAdmin?: boolean;
}) => {
  const t = useTranslations("admin.tokenRateLimits");
  const { data, isLoading, error } = useSWR<TokenRateLimitDisplay[]>(
    fetchUrl,
    errorHandlingFetcher
  );

  if (isLoading) {
    return <PageLoader />;
  }

  if (!isLoading && error) {
    return <Text as="p">{t("limits.loadFailed.error")}</Text>;
  }

  let processedData = data;
  if (responseMapper) {
    processedData = responseMapper(data);
  }

  return (
    <TokenRateLimitTable
      tokenRateLimits={processedData ?? []}
      fetchUrl={fetchUrl}
      description={description}
      hideHeading={hideHeading}
      isAdmin={isAdmin}
    />
  );
};
