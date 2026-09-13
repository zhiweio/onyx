"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import {
  Card,
  CopyButton,
  InputTypeIn,
  MessageCard,
  Modal,
  Table,
  Tag,
  Text,
  Tooltip,
  createTableColumns,
} from "@opal/components";
import { IllustrationContent, toast } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { getMcpGatewayCall, listMcpGatewayCalls } from "@/lib/mcp-catalog/api";
import type {
  McpGatewayCallDetail,
  McpGatewayCallItem,
} from "@/lib/mcp-catalog/types";
import type { DateRange } from "@/refresh-components/DateRangePicker";
import { formatJsonValue, parseArgumentsPreview } from "./callDisplay";
import { isoWindowForInclusiveDateRange } from "./dateWindow";
import { errorMessage, formatBytes, formatLatency, PAGE_SIZE } from "./format";
import {
  BilledTag,
  DateTimeCell,
  MetricCell,
  OutcomeTag,
  ServerTagCell,
  TruncatedTextCell,
  outcomeColor,
  outcomeLabel,
} from "./GatewayTableCells";
import { useDebouncedValue } from "./useDebouncedValue";

const tc = createTableColumns<McpGatewayCallItem>();
const MAX_VISIBLE_ARGUMENT_TAGS = 2;

interface GatewayCallsTableProps {
  dateRange: DateRange;
  catalogSlug: string;
  tool: string;
}

interface ArgumentsPreviewCellProps {
  preview: string;
  empty: string;
  moreLabel: (count: number) => string;
}

function ArgumentsPreviewCell({
  preview,
  empty,
  moreLabel,
}: ArgumentsPreviewCellProps) {
  const pairs = parseArgumentsPreview(preview);
  if (pairs.length === 0) {
    if (!preview) {
      return (
        <Text font="secondary-body" color="text-03">
          {empty}
        </Text>
      );
    }
    return (
      <Tooltip tooltip={preview}>
        <Text font="secondary-mono" color="text-03" nowrap>
          {preview}
        </Text>
      </Tooltip>
    );
  }

  const summary = pairs.map((pair) => `${pair.key}=${pair.value}`).join(" · ");
  const visible = pairs.slice(0, MAX_VISIBLE_ARGUMENT_TAGS);
  const hidden = pairs.slice(MAX_VISIBLE_ARGUMENT_TAGS);

  return (
    <Tooltip tooltip={summary}>
      <div className="flex w-full min-w-0 items-center gap-1 overflow-hidden">
        {visible.map((pair) => (
          <Tag
            key={pair.key}
            title={pair.key}
            value={pair.value}
            truncate
            tooltip={summary}
          />
        ))}
        {hidden.length > 0 ? (
          <Tag title={moreLabel(hidden.length)} tooltip={summary} />
        ) : null}
      </div>
    </Tooltip>
  );
}

interface DetailFieldProps {
  label: string;
  value: string | null | undefined;
  empty: string;
  copyable?: boolean;
}

function DetailField({
  label,
  value,
  empty,
  copyable = false,
}: DetailFieldProps) {
  const display = value || empty;
  const canCopy = copyable && Boolean(value);

  return (
    <Card padding={2} rounding={3} background="heavy">
      <div className="flex min-w-0 flex-col gap-1">
        <Text as="p" font="secondary-body" color="text-03">
          {label}
        </Text>
        <div className="flex min-w-0 items-start gap-1">
          <Text
            as="p"
            font="secondary-mono"
            color={value ? "text-05" : "text-03"}
            wordWrap="break-all"
          >
            {display}
          </Text>
          {canCopy ? (
            <CopyButton size="xs" getCopyText={() => value ?? ""} />
          ) : null}
        </div>
      </div>
    </Card>
  );
}

interface JsonBlockProps {
  value: Record<string, unknown> | null;
  testId?: string;
}

function JsonBlock({ value, testId }: JsonBlockProps) {
  const text = formatJsonValue(value);
  return (
    <div
      className="relative rounded-12 border border-border-01 bg-background-tint-00"
      data-testid={testId}
    >
      <div className="absolute end-2 top-2 z-1">
        <CopyButton size="xs" getCopyText={() => text} />
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre break-normal p-3 pe-10 font-secondary-mono text-text-03">
        {text}
      </pre>
    </div>
  );
}

interface CallDetailModalProps {
  row: McpGatewayCallItem;
  detail: McpGatewayCallDetail | null;
  isLoading: boolean;
  onClose: () => void;
}

function CallDetailModal({
  row,
  detail,
  isLoading,
  onClose,
}: CallDetailModalProps) {
  const t = useTranslations("admin.mcpGateway");
  const format = useFormatter();
  const source = detail ?? row;
  const errorText = source.error_message;
  const identifierFields = [
    {
      key: "requestId",
      label: t("calls.requestId"),
      value: detail?.request_id,
      copyable: true,
    },
    {
      key: "cacheKey",
      label: t("calls.cacheKey"),
      value: source.cache_key,
      copyable: true,
    },
    {
      key: "userEmail",
      label: t("calls.userEmail"),
      value: source.user_email,
      copyable: false,
    },
    {
      key: "sessionId",
      label: t("calls.sessionId"),
      value: source.session_id,
      copyable: true,
    },
    {
      key: "packSlug",
      label: t("calls.packSlug"),
      value: detail?.pack_slug,
      copyable: false,
    },
    {
      key: "refreshMode",
      label: t("calls.refreshMode"),
      value: detail?.refresh_mode,
      copyable: false,
    },
    {
      key: "parentCallId",
      label: t("calls.parentCallId"),
      value: detail?.parent_call_id,
      copyable: true,
    },
    {
      key: "resultBlobId",
      label: t("calls.resultBlobId"),
      value: detail?.result_blob_id,
      copyable: true,
    },
  ].filter((field) => Boolean(field.value));

  return (
    <Modal open onOpenChange={(open) => !open && onClose()}>
      <Modal.Content width="xl" height="lg">
        <Modal.Header
          icon={ADMIN_ROUTES.MCP_GATEWAY.icon}
          title={t("calls.detailTitle")}
          description={t("calls.detailDescription", {
            tool: source.effective_tool_name || t("calls.missing"),
            server: source.catalog_slug || t("calls.missing"),
          })}
          onClose={onClose}
        />
        <Modal.Body>
          <div
            className="flex flex-col gap-4"
            data-testid="mcp-gateway-call-detail"
          >
            <Card border="solid" rounding={4} padding={3}>
              <div className="flex flex-col gap-3">
                <Text as="p" font="main-ui-action">
                  {source.effective_tool_name || t("calls.missing")}
                </Text>
                <div className="flex flex-wrap items-center gap-2">
                  <Tag
                    title={outcomeLabel(t, source.outcome)}
                    color={outcomeColor(source.outcome)}
                  />
                  <Tag
                    title={t("calls.billed")}
                    value={
                      source.upstream_billed
                        ? t("calls.billedYes")
                        : t("calls.billedNo")
                    }
                    color={source.upstream_billed ? "amber" : "gray"}
                  />
                  <Text font="secondary-body" color="text-03">
                    {t("calls.latencyMs", { ms: source.latency_ms })}
                  </Text>
                  <Text font="secondary-body" color="text-03">
                    {formatBytes(source.response_bytes)}
                  </Text>
                  <Text font="secondary-body" color="text-03">
                    {format.dateTime(new Date(source.created_at), {
                      dateStyle: "medium",
                      timeStyle: "medium",
                    })}
                  </Text>
                </div>
              </div>
            </Card>

            {errorText ? (
              <MessageCard
                variant="error"
                title={t("calls.errorMessage")}
                description={errorText}
                titleMaxLines={undefined}
              />
            ) : null}

            {identifierFields.length > 0 ? (
              <div className="flex flex-col gap-2">
                <Text as="p" font="secondary-action">
                  {t("calls.identifiers")}
                </Text>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {identifierFields.map((field) => (
                    <DetailField
                      key={field.key}
                      label={field.label}
                      value={field.value}
                      empty={t("calls.missing")}
                      copyable={field.copyable}
                    />
                  ))}
                </div>
              </div>
            ) : null}

            <div className="flex flex-col gap-2">
              <Text as="p" font="secondary-action">
                {t("calls.arguments")}
              </Text>
              {detail ? (
                <JsonBlock value={detail.arguments} />
              ) : (
                <Text as="p" font="secondary-body" color="text-03">
                  {isLoading ? t("calls.loadingDetail") : t("calls.missing")}
                </Text>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Text as="p" font="secondary-action">
                {t("calls.payload")}
              </Text>
              {detail ? (
                <JsonBlock value={detail.payload ?? null} />
              ) : (
                <Text as="p" font="secondary-body" color="text-03">
                  {isLoading ? t("calls.loadingDetail") : t("calls.missing")}
                </Text>
              )}
            </div>
          </div>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}

export default function GatewayCallsTable({
  dateRange,
  catalogSlug,
  tool,
}: GatewayCallsTableProps) {
  const t = useTranslations("admin.mcpGateway");
  const [searchInput, setSearchInput] = useState("");
  const searchTerm = useDebouncedValue(searchInput);
  const isoWindow =
    dateRange?.from && dateRange.to
      ? isoWindowForInclusiveDateRange(dateRange)
      : undefined;
  const fromIso = isoWindow?.from;
  const toIso = isoWindow?.to;
  const filterKey = `${fromIso}\0${toIso}\0${catalogSlug}\0${tool}\0${searchTerm}`;
  const [filterSnapshot, setFilterSnapshot] = useState(filterKey);
  const [pageIndex, setPageIndex] = useState(0);
  const nextPageIndex = filterSnapshot !== filterKey ? 0 : pageIndex;
  if (filterSnapshot !== filterKey) {
    setFilterSnapshot(filterKey);
    setPageIndex(0);
  }
  const [rows, setRows] = useState<McpGatewayCallItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedRow, setSelectedRow] = useState<McpGatewayCallItem | null>(
    null
  );
  const [detail, setDetail] = useState<McpGatewayCallDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    if (!fromIso || !toIso) return;
    const id = ++requestId.current;
    setIsLoading(true);
    try {
      const result = await listMcpGatewayCalls({
        from: fromIso,
        to: toIso,
        catalog_slug: catalogSlug || undefined,
        tool: tool || undefined,
        q: searchTerm || undefined,
        offset: nextPageIndex * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      if (id !== requestId.current) return;
      setRows(result.items);
      setTotal(result.total);
    } catch (error) {
      if (id !== requestId.current) return;
      toast.error(errorMessage(error, t("toasts.loadFailed")));
    } finally {
      if (id === requestId.current) setIsLoading(false);
    }
  }, [fromIso, toIso, catalogSlug, tool, searchTerm, nextPageIndex, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns = useMemo(
    () => [
      tc.column("created_at", {
        header: t("calls.time"),
        weight: 12,
        enableSorting: false,
        cell: (value) => <DateTimeCell value={value} />,
      }),
      tc.column("catalog_slug", {
        header: t("calls.server"),
        weight: 12,
        enableSorting: false,
        cell: (value) => (
          <ServerTagCell value={value} empty={t("calls.missing")} />
        ),
      }),
      tc.column("effective_tool_name", {
        header: t("calls.tool"),
        weight: 18,
        enableSorting: false,
        cell: (value) => (
          <TruncatedTextCell value={value} empty={t("calls.missing")} mono />
        ),
      }),
      tc.column("outcome", {
        header: t("calls.outcome"),
        weight: 9,
        enableSorting: false,
        cell: (value) => <OutcomeTag outcome={value} />,
      }),
      tc.column("latency_ms", {
        header: t("calls.latency"),
        weight: 8,
        enableSorting: false,
        cell: (value) => <MetricCell value={formatLatency(value)} />,
      }),
      tc.column("response_bytes", {
        header: t("calls.size"),
        weight: 8,
        enableSorting: false,
        cell: (value) => <MetricCell value={formatBytes(value)} />,
      }),
      tc.column("upstream_billed", {
        header: t("calls.billed"),
        weight: 7,
        enableSorting: false,
        cell: (value) => <BilledTag billed={value} />,
      }),
      tc.column("arguments_preview", {
        header: t("calls.preview"),
        weight: 26,
        enableSorting: false,
        cell: (value) => (
          <ArgumentsPreviewCell
            preview={value || ""}
            empty={t("calls.missing")}
            moreLabel={(count) => t("calls.moreParams", { count })}
          />
        ),
      }),
    ],
    [t]
  );

  return (
    <div
      className="flex flex-col gap-3 pt-4"
      data-testid="mcp-gateway-calls-table"
    >
      <InputTypeIn
        searchIcon
        value={searchInput}
        onChange={(event) => setSearchInput(event.target.value)}
        placeholder={t("calls.searchPlaceholder")}
        aria-label={t("calls.searchPlaceholder")}
        data-testid="mcp-gateway-calls-search"
      />
      <Table
        key={`${fromIso}|${toIso}|${catalogSlug}|${tool}`}
        data={rows}
        columns={columns}
        getRowId={(row) => String(row.id)}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={searchTerm}
        footer={{ units: t("table.footerUnits") }}
        onRowClick={(row) => {
          setSelectedRow(row);
          setDetail(null);
          setDetailLoading(true);
          void getMcpGatewayCall(row.id)
            .then(setDetail)
            .catch((error) =>
              toast.error(errorMessage(error, t("toasts.loadFailed")))
            )
            .finally(() => setDetailLoading(false));
        }}
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={isLoading ? t("table.loading") : t("calls.empty")}
          />
        }
        serverSide={{
          totalItems: total,
          isLoading,
          onSortingChange: () => undefined,
          onPaginationChange: (nextPage) => setPageIndex(nextPage),
          onSearchTermChange: () => undefined,
        }}
      />
      {selectedRow ? (
        <CallDetailModal
          row={selectedRow}
          detail={detail}
          isLoading={detailLoading}
          onClose={() => {
            setSelectedRow(null);
            setDetail(null);
            setDetailLoading(false);
          }}
        />
      ) : null}
    </div>
  );
}
