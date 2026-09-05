"use client";

import useSWR from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";
import type {
  ReportTemplate,
  ReportTemplateListResponse,
} from "@/lib/report-templates/types";

export function useReportTemplates() {
  const { data, error, isLoading, mutate } = useSWR<ReportTemplateListResponse>(
    SWR_KEYS.reportTemplates,
    errorHandlingFetcher
  );

  return {
    data: data?.templates ?? [],
    error,
    isLoading,
    refresh: mutate,
  };
}

export function useReportTemplate(templateId: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<ReportTemplate>(
    templateId ? SWR_KEYS.reportTemplate(templateId) : null,
    errorHandlingFetcher
  );

  return {
    data,
    error,
    isLoading,
    refresh: mutate,
  };
}
