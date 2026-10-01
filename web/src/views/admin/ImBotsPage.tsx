"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import { Button, Card, Switch, Tag, Text } from "@opal/components";
import {
  ContentAction,
  InputHorizontal,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import { SvgDiscord, SvgSlack } from "@opal/icons";
import { SvgDingTalk, SvgFeishu, SvgWeCom } from "@opal/logos";
import type { IconFunctionComponent } from "@opal/types";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";
import { useSettings } from "@/lib/settings/hooks";
import { updateAdminSettings } from "@/lib/settings/svc";
import type { Settings } from "@/lib/settings/types";

const route = ADMIN_ROUTES.IM_BOTS;

interface PlatformMeta {
  platform: string;
  label: string;
  icon: IconFunctionComponent;
}

const PLATFORMS: PlatformMeta[] = [
  { platform: "wecom", label: "WeCom", icon: SvgWeCom },
  { platform: "dingtalk", label: "DingTalk", icon: SvgDingTalk },
  { platform: "feishu", label: "Feishu", icon: SvgFeishu },
];

interface ChinaBotPlatformStatus {
  platform: string;
  provider_count: number;
  bot_ready: boolean;
  app_id: string | null;
  bound_users: number;
}

interface ChinaBotsStatusResponse {
  platforms: ChinaBotPlatformStatus[];
}

function callbackUrl(platform: string): string {
  return `${window.location.origin}/onyxbot/${platform}/callback`;
}

function PlatformCard({ meta }: { meta: PlatformMeta }) {
  const t = useTranslations("admin.imBots");
  const [verifying, setVerifying] = useState(false);

  const { data, isLoading, mutate } = useSWR<ChinaBotsStatusResponse>(
    SWR_KEYS.adminOnyxbotChinaStatus,
    errorHandlingFetcher
  );
  const status = data?.platforms.find((p) => p.platform === meta.platform);

  const verify = async () => {
    setVerifying(true);
    try {
      const res = await fetch(
        `/api/admin/onyxbot-china/${meta.platform}/verify`,
        {
          method: "POST",
        }
      );
      // SAFETY: the verify endpoint always answers {ok, detail}, error or not.
      const body = (await res.json()) as { ok: boolean; detail: string | null };
      if (body.ok) {
        toast.success(t("verify.ok"));
      } else {
        toast.error(body.detail ?? t("verify.failed"));
      }
    } catch {
      toast.error(t("verify.failed"));
    } finally {
      setVerifying(false);
    }
  };

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(callbackUrl(meta.platform));
      toast.success(t("callbackUrl.copied"));
    } catch {
      toast.error(t("callbackUrl.copyFailed"));
    }
  };

  const stateTag = isLoading ? null : !status?.provider_count ? (
    <Tag title={t("status.noProvider")} color="gray" />
  ) : status.bot_ready ? (
    <Tag title={t("status.ready")} color="green" />
  ) : (
    <Tag title={t("status.notReady")} color="amber" />
  );

  return (
    <Card border="solid" rounding={4} padding={2}>
      <ContentAction
        icon={meta.icon}
        title={meta.label}
        description={
          status?.app_id
            ? t("status.appId", { appId: status.app_id })
            : t("status.noProvider")
        }
        sizePreset="main-ui"
        variant="section"
        padding={0}
        rightChildren={
          <div className="flex flex-wrap items-center gap-2">
            {stateTag}
            {typeof status?.bound_users === "number" && (
              <Tag
                title={t("status.boundUsers", { count: status.bound_users })}
                color="blue"
              />
            )}
            <Button
              prominence="internal"
              disabled={verifying || !status?.bot_ready}
              onClick={() => void verify()}
            >
              {verifying ? t("verify.buttonRunning") : t("verify.button")}
            </Button>
            <Button
              prominence="secondary"
              href={ADMIN_ROUTES.SSO_PROVIDERS.path}
            >
              {t("configureButton")}
            </Button>
          </div>
        }
      />
      <div className="flex items-center justify-between gap-2 pt-2 pl-2">
        <div className="min-w-0 truncate font-mono text-sm text-text-03">
          {callbackUrl(meta.platform)}
        </div>
        <Button prominence="internal" onClick={() => void copyUrl()}>
          {t("callbackUrl.copyButton")}
        </Button>
      </div>
      <p className="pl-2 pt-1 text-xs text-text-04">{t("callbackUrl.hint")}</p>
    </Card>
  );
}

interface VisibilityToggleProps {
  field: "slack_integration_visible" | "discord_integration_visible";
  title: string;
  description: string;
  icon: IconFunctionComponent;
}

function VisibilityToggle({
  field,
  title,
  description,
  icon,
}: VisibilityToggleProps) {
  const t = useTranslations("admin.imBots");
  const settings = useSettings();
  const [pending, setPending] = useState(false);

  const save = async (checked: boolean) => {
    setPending(true);
    try {
      // SAFETY: `field` is one of the two Settings visibility booleans by
      // prop type, so the partial is always a valid Settings subset.
      await updateAdminSettings({ [field]: checked } as Partial<Settings>);
      toast.success(t("visibility.saved"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("visibility.saveFailed"));
    } finally {
      setPending(false);
    }
  };

  return (
    <Card border="solid" rounding={4}>
      <InputHorizontal
        icon={icon}
        title={title}
        description={description}
        disabled={pending}
        withLabel
      >
        <Switch
          checked={settings?.[field] ?? false}
          onCheckedChange={(checked) => void save(checked)}
          disabled={pending}
        />
      </InputHorizontal>
    </Card>
  );
}

export default function ImBotsPage() {
  const t = useTranslations("admin.imBots");
  const adminRouteTitle = useAdminRouteTitle();

  return (
    <SettingsLayouts.Root data-testid="im-bots-page">
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        description={t("header.description")}
        divider
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-2">
          {PLATFORMS.map((meta) => (
            <PlatformCard key={meta.platform} meta={meta} />
          ))}

          <div className="pt-4">
            <Text font="main-ui-action" color="text-03">
              {t("visibility.title")}
            </Text>
          </div>
          <VisibilityToggle
            field="slack_integration_visible"
            title={t("visibility.slack.title")}
            description={t("visibility.slack.description")}
            icon={SvgSlack}
          />
          <VisibilityToggle
            field="discord_integration_visible"
            title={t("visibility.discord.title")}
            description={t("visibility.discord.description")}
            icon={SvgDiscord}
          />
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
