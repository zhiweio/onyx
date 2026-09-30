"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Card, Text } from "@opal/components";
import { SettingsLayouts, toast } from "@opal/layouts";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

export interface AgentModelView {
  model_id: string;
  provider: string;
  display_name: string;
  context_window: number;
  max_output_tokens: number;
  runtimes: string[];
  is_default: boolean;
  notes: string;
  overlay: {
    id: number;
    name: string;
    template_model_id: string;
    base_url: string | null;
    enabled: boolean;
    verified_at: string | null;
    verify_error: string | null;
  } | null;
}

export interface OverlayDraft {
  name: string;
  provider: string;
  template_model_id: string;
  model_id: string;
  base_url: string;
  context_window: string;
  max_output_tokens: string;
}

const EMPTY_DRAFT: OverlayDraft = {
  name: "",
  provider: "",
  template_model_id: "",
  model_id: "",
  base_url: "",
  context_window: "",
  max_output_tokens: "",
};

async function callApi<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `HTTP ${resp.status}`);
  }
  return resp.json() as Promise<T>;
}

export default function AgentModelsPage() {
  const t = useTranslations("admin.agentModels");
  const adminRouteTitle = useAdminRouteTitle();
  const route = ADMIN_ROUTES.AGENT_MODELS;
  const [models, setModels] = useState<AgentModelView[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState<OverlayDraft>(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await callApi<{ models: AgentModelView[] }>(
        "/api/admin/agent-models"
      );
      setModels(data.models);
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createOverlay = async () => {
    setBusy(true);
    try {
      await callApi("/api/admin/agent-models", {
        method: "POST",
        body: JSON.stringify({
          name: draft.name,
          provider: draft.provider,
          template_model_id: draft.template_model_id,
          model_id: draft.model_id || undefined,
          base_url: draft.base_url || null,
          context_window: draft.context_window
            ? Number(draft.context_window)
            : null,
          max_output_tokens: draft.max_output_tokens
            ? Number(draft.max_output_tokens)
            : null,
        }),
      });
      toast.success(t("created"));
      setDraft(EMPTY_DRAFT);
      await refresh();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (overlayId: number) => {
    setBusy(true);
    try {
      const row = await callApi<{
        verified_at: string | null;
        verify_error: string | null;
      }>(`/api/admin/agent-models/${overlayId}/verify`, { method: "POST" });
      if (row.verified_at) {
        toast.success(t("verified"));
      } else {
        toast.error(`${t("verifyFailed")}: ${row.verify_error ?? ""}`);
      }
      await refresh();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (overlayId: number) => {
    setBusy(true);
    try {
      await callApi(`/api/admin/agent-models/${overlayId}`, {
        method: "DELETE",
      });
      toast.success(t("deleted"));
      await refresh();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setBusy(false);
    }
  };

  const catalog = models.filter((m) => !m.overlay);
  const overlays = models.filter((m) => m.overlay);

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        divider
      />
      <SettingsLayouts.Body>
        <Text font="secondary-body" color="text-03">
          {t("subtitle")}
        </Text>

        <Card className="p-3">
          <div className="mb-2 flex items-center justify-between">
            <Text font="main-ui-body">{t("catalog")}</Text>
            <Button
              size="xs"
              prominence="tertiary"
              onClick={() => void refresh()}
              disabled={loading}
            >
              {t("refresh")}
            </Button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-03">
                  <th className="p-2">{t("col.model")}</th>
                  <th className="p-2">{t("col.provider")}</th>
                  <th className="p-2">{t("col.context")}</th>
                  <th className="p-2">{t("col.runtimes")}</th>
                </tr>
              </thead>
              <tbody>
                {catalog.map((model) => (
                  <tr key={model.model_id} className="border-t border-border-01">
                    <td className="p-2">
                      {model.display_name}
                      {model.is_default ? (
                        <span className="ml-1 text-status-success-05">
                          ({t("default")})
                        </span>
                      ) : null}
                    </td>
                    <td className="p-2">{model.provider}</td>
                    <td className="p-2">{model.context_window.toLocaleString()}</td>
                    <td className="p-2">{model.runtimes.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="p-3">
          <Text font="main-ui-body">{t("overlays")}</Text>
          {overlays.length === 0 ? (
            <Text font="secondary-body" color="text-03">
              {t("noOverlays")}
            </Text>
          ) : (
            <div className="mt-2 space-y-2">
              {overlays.map((model) => (
                <div
                  key={model.model_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-12 border border-border-01 p-2"
                >
                  <div className="min-w-0">
                    <Text font="main-ui-body" truncate>
                      {model.display_name}
                      <span className="ml-1 text-text-03">
                        ({model.overlay?.template_model_id})
                      </span>
                    </Text>
                    {model.overlay?.verified_at ? (
                      <Text font="secondary-body" color="status-success-05">
                        {t("verifiedAt", {
                          time: new Date(model.overlay.verified_at).toLocaleString(),
                        })}
                      </Text>
                    ) : model.overlay?.verify_error ? (
                      <Text font="secondary-body" color="status-error-05">
                        {t("verifyError")}: {model.overlay.verify_error}
                      </Text>
                    ) : (
                      <Text font="secondary-body" color="text-03">
                        {t("notVerified")}
                      </Text>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <Button
                      size="xs"
                      prominence="secondary"
                      disabled={busy}
                      onClick={() => void verify(model.overlay!.id)}
                    >
                      {t("verify")}
                    </Button>
                    <Button
                      size="xs"
                      prominence="tertiary"
                      disabled={busy}
                      onClick={() => void remove(model.overlay!.id)}
                    >
                      {t("delete")}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-3">
            <input
              className="rounded-12 border border-border-01 bg-background-neutral-00 p-2"
              placeholder={t("form.name")}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
            <input
              className="rounded-12 border border-border-01 bg-background-neutral-00 p-2"
              placeholder={t("form.provider")}
              value={draft.provider}
              onChange={(e) => setDraft({ ...draft, provider: e.target.value })}
            />
            <input
              className="rounded-12 border border-border-01 bg-background-neutral-00 p-2"
              placeholder={t("form.template")}
              value={draft.template_model_id}
              onChange={(e) =>
                setDraft({ ...draft, template_model_id: e.target.value })
              }
            />
            <input
              className="rounded-12 border border-border-01 bg-background-neutral-00 p-2"
              placeholder={t("form.baseUrl")}
              value={draft.base_url}
              onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
            />
            <input
              className="rounded-12 border border-border-01 bg-background-neutral-00 p-2"
              placeholder={t("form.context")}
              value={draft.context_window}
              onChange={(e) =>
                setDraft({ ...draft, context_window: e.target.value })
              }
            />
            <input
              className="rounded-12 border border-border-01 bg-background-neutral-00 p-2"
              placeholder={t("form.maxOutput")}
              value={draft.max_output_tokens}
              onChange={(e) =>
                setDraft({ ...draft, max_output_tokens: e.target.value })
              }
            />
          </div>
          <div className="mt-2">
            <Button
              size="xs"
              prominence="secondary"
              disabled={busy || !draft.name || !draft.provider || !draft.template_model_id}
              onClick={() => void createOverlay()}
            >
              {t("add")}
            </Button>
          </div>
        </Card>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
