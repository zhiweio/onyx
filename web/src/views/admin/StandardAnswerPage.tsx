"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Card, Text } from "@opal/components";
import { SettingsLayouts, toast } from "@opal/layouts";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

interface StandardAnswerRow {
  id: number;
  keyword: string;
  answer: string;
  active: boolean;
  category_ids: number[];
}

interface CategoryRow {
  id: number;
  name: string;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  return resp.json() as Promise<T>;
}

export default function StandardAnswerPage() {
  const t = useTranslations("admin.standardAnswers");
  const adminRouteTitle = useAdminRouteTitle();
  const route = ADMIN_ROUTES.STANDARD_ANSWERS;
  const [answers, setAnswers] = useState<StandardAnswerRow[]>([]);
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [keyword, setKeyword] = useState("");
  const [answer, setAnswer] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [newCategory, setNewCategory] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [a, c] = await Promise.all([
        api<StandardAnswerRow[]>("/api/admin/standard-answers"),
        api<CategoryRow[]>("/api/admin/standard-answers/categories"),
      ]);
      setAnswers(a);
      setCategories(c);
    } catch (err) {
      toast.error(String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = async () => {
    setBusy(true);
    try {
      await api("/api/admin/standard-answers", {
        method: "POST",
        body: JSON.stringify({
          keyword,
          answer,
          category_ids: categoryId ? [categoryId] : [],
        }),
      });
      toast.success(t("created"));
      setKeyword("");
      setAnswer("");
      await refresh();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setBusy(false);
    }
  };

  const createCategory = async () => {
    if (!newCategory.trim()) return;
    setBusy(true);
    try {
      await api("/api/admin/standard-answers/categories", {
        method: "POST",
        body: JSON.stringify({ name: newCategory.trim() }),
      });
      toast.success(t("categoryCreated"));
      setNewCategory("");
      await refresh();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (row: StandardAnswerRow) => {
    setBusy(true);
    try {
      await api(`/api/admin/standard-answers/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify({ active: !row.active }),
      });
      await refresh();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: StandardAnswerRow) => {
    setBusy(true);
    try {
      await api(`/api/admin/standard-answers/${row.id}`, { method: "DELETE" });
      toast.success(t("deleted"));
      await refresh();
    } catch (err) {
      toast.error(String(err));
    } finally {
      setBusy(false);
    }
  };

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
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Text font="main-ui-body">{t("categories")}</Text>
            {categories.map((cat) => (
              <span
                key={cat.id}
                className={`rounded-12 border px-2 py-1 text-sm ${
                  categoryId === cat.id
                    ? "border-accent-10 bg-accent-0"
                    : "border-border-01"
                }`}
              >
                <button type="button" onClick={() => setCategoryId(cat.id === categoryId ? null : cat.id)}>
                  {cat.name}
                </button>
              </span>
            ))}
            <input
              className="w-40 rounded-12 border border-border-01 bg-background-neutral-00 p-1 text-sm"
              placeholder={t("newCategory")}
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
            />
            <Button size="xs" prominence="tertiary" disabled={busy} onClick={() => void createCategory()}>
              {t("addCategory")}
            </Button>
          </div>

          <div className="space-y-2">
            {answers.map((row) => (
              <div
                key={row.id}
                className="rounded-12 border border-border-01 p-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Text font="main-ui-body" className="font-medium">
                    {row.keyword}
                    {!row.active ? (
                      <span className="ml-1 text-text-03">({t("inactive")})</span>
                    ) : null}
                  </Text>
                  <div className="flex gap-1">
                    <Button size="xs" prominence="tertiary" disabled={busy} onClick={() => void toggle(row)}>
                      {row.active ? t("disable") : t("enable")}
                    </Button>
                    <Button size="xs" prominence="tertiary" disabled={busy} onClick={() => void remove(row)}>
                      {t("delete")}
                    </Button>
                  </div>
                </div>
                <Text font="secondary-body" color="text-03">
                  {row.answer}
                </Text>
              </div>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-1 gap-2">
            <input
              className="rounded-12 border border-border-01 bg-background-neutral-00 p-2"
              placeholder={t("form.keyword")}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <textarea
              className="min-h-24 rounded-12 border border-border-01 bg-background-neutral-00 p-2"
              placeholder={t("form.answer")}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
            />
            <div>
              <Button
                size="xs"
                prominence="secondary"
                disabled={busy || !keyword.trim() || !answer.trim()}
                onClick={() => void create()}
              >
                {t("add")}
              </Button>
            </div>
          </div>
        </Card>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
