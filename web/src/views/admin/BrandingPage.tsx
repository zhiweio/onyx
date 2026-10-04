"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { mutate } from "swr";
import { useRouter } from "next/navigation";
import { SettingsLayouts, toast } from "@opal/layouts";
import { Section } from "@/layouts/general-layouts";
import {
  Button,
  Card,
  Divider,
  InputTextArea,
  InputTypeIn,
  Switch,
  Text,
} from "@opal/components";
import { InputHorizontal, InputVertical } from "@opal/layouts";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { SvgAddLines, SvgRevert, SvgX } from "@opal/icons";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { useSettings } from "@/lib/settings/hooks";
import { SWR_KEYS } from "@/lib/swr-keys";
import type {
  EnterpriseSettings,
  LogoDisplayStyle,
} from "@/lib/settings/types";
import {
  BrandAssetSlot,
  brandAssetUrl,
  deleteBrandAsset,
  updateEnterpriseSettings,
  uploadBrandAsset,
} from "@/lib/settings/enterpriseSvc";
import { buildBrandThemeCss } from "@/lib/branding/theme";

const route = ADMIN_ROUTES.BRANDING;

const LOGO_DISPLAY_STYLES: LogoDisplayStyle[] = [
  "logo_and_name",
  "logo_only",
  "name_only",
];

const IMAGE_INPUT_ACCEPT =
  ".png,.jpg,.jpeg,.webp,.svg,.ico,image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon";

const PREVIEW_STYLE_ID = "onyx-brand-preview";

/**
 * One brand-asset slot: rectangular preview when the asset is a wordmark,
 * square crop for marks and favicons. Upload + remove hit the dedicated
 * asset endpoints; the preview URL carries a cache-buster so a fresh upload
 * replaces the previous image immediately.
 */
function AssetField({
  title,
  description,
  currentFlag,
  slot,
  rectangular,
  onUploaded,
  onRemoved,
}: {
  title: string;
  description: string;
  currentFlag: boolean | null | undefined;
  slot: BrandAssetSlot;
  rectangular?: boolean;
  onUploaded: () => void;
  onRemoved: () => void;
}) {
  const t = useTranslations("admin_branding.assets");
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  // Bumped after each mutation so the preview <img> refetches the endpoint.
  const [version, setVersion] = useState(0);

  const pickFile = () => {
    inputRef.current?.click();
  };

  const handleFile = async (file: File) => {
    setBusy(true);
    try {
      await uploadBrandAsset(slot, file);
      setVersion((v) => v + 1);
      onUploaded();
      toast.success(t("uploadSuccess"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("uploadFailed"));
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async () => {
    setBusy(true);
    try {
      await deleteBrandAsset(slot);
      setVersion((v) => v + 1);
      onRemoved();
      toast.success(t("removeSuccess"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("removeFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-y-2">
      <Text font="main-ui-body" color="text-03">
        {title}
      </Text>
      <div className="flex items-center gap-4">
        <div
          className={
            rectangular
              ? "h-14 w-44 border border-border-01 rounded-08 bg-background-neutral-00 flex items-center justify-center overflow-hidden"
              : "h-14 w-14 border border-border-01 rounded-full bg-background-neutral-00 flex items-center justify-center overflow-hidden"
          }
        >
          {currentFlag ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={version}
              src={brandAssetUrl(slot)}
              alt={title}
              className={
                rectangular
                  ? "max-h-12 max-w-40 object-contain"
                  : "h-full w-full object-cover"
              }
            />
          ) : (
            <Text font="main-ui-body" color="text-05">
              {t("empty.label")}
            </Text>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Button
            prominence="secondary"
            disabled={busy}
            onClick={pickFile}
            icon={SvgAddLines}
          >
            {currentFlag ? t("replace.label") : t("upload.label")}
          </Button>
          {currentFlag && (
            <Button
              prominence="tertiary"
              disabled={busy}
              onClick={handleRemove}
              icon={SvgX}
            >
              {t("remove.label")}
            </Button>
          )}
        </div>
      </div>
      <Text font="secondary-body" color="text-03">
        {description}
      </Text>
      <input
        ref={inputRef}
        type="file"
        accept={IMAGE_INPUT_ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) void handleFile(file);
        }}
      />
    </div>
  );
}

function ColorField({
  title,
  description,
  value,
  onChange,
}: {
  title: string;
  description: string;
  value: string | null;
  onChange: (value: string | null) => void;
}) {
  const hex = value ?? "";
  const swatch = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : "#000000";
  return (
    <InputVertical title={title} description={description} withLabel>
      <div className="flex items-center gap-2 w-full">
        <input
          type="color"
          value={swatch}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 w-10 rounded-04 border border-border-01 bg-transparent cursor-pointer"
          aria-label={title}
        />
        <div className="flex-1">
          <InputTypeIn
            value={hex}
            placeholder="#0055FF"
            onChange={(e) => onChange(e.target.value || null)}
          />
        </div>
        <Button
          prominence="tertiary"
          icon={SvgRevert}
          disabled={value === null}
          onClick={() => onChange(null)}
        />
      </div>
    </InputVertical>
  );
}

/**
 * Live preview of unsaved brand colors: mirrors the server-side injection
 * (root layout) through a second <style> tag that only exists while the
 * draft differs from the saved values.
 */
function useBrandColorPreview(
  brandColor: string | null | undefined,
  brandColorDark: string | null | undefined
) {
  const { enterprise } = useSettings();
  const savedLight = enterprise?.brand_color ?? null;
  const savedDark = enterprise?.brand_color_dark ?? null;

  const previewCss = useMemo(
    () => buildBrandThemeCss({ brandColor, brandColorDark }),
    [brandColor, brandColorDark]
  );
  const savedCss = useMemo(
    () =>
      buildBrandThemeCss({ brandColor: savedLight, brandColorDark: savedDark }),
    [savedLight, savedDark]
  );

  useEffect(() => {
    if (!previewCss || previewCss === savedCss) return;
    // SAFETY: this id is only ever set on a <style> element created below.
    let tag = document.getElementById(
      PREVIEW_STYLE_ID
    ) as HTMLStyleElement | null;
    if (!tag) {
      tag = document.createElement("style");
      tag.id = PREVIEW_STYLE_ID;
      document.head.appendChild(tag);
    }
    tag.textContent = previewCss;
    return () => {
      tag?.remove();
    };
  }, [previewCss, savedCss]);
}

export default function BrandingPage() {
  const t = useTranslations("admin_branding");
  const router = useRouter();
  const adminRouteTitle = useAdminRouteTitle();
  const { enterprise, isLoading } = useSettings();

  // Draft mirrors the stored settings once loaded; every section saves its
  // own slice, so unsaved edits in one card never leak into another save.
  const [draft, setDraft] = useState<EnterpriseSettings | null>(null);
  useEffect(() => {
    if (enterprise && draft === null) {
      setDraft(enterprise);
    }
  }, [enterprise, draft]);

  const [saving, setSaving] = useState(false);

  const updateDraft = useCallback((patch: Partial<EnterpriseSettings>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current));
  }, []);

  const saveFields = useCallback(
    async (patch: Partial<EnterpriseSettings>) => {
      setSaving(true);
      try {
        const updated = await updateEnterpriseSettings(patch);
        setDraft(updated);
        await mutate(SWR_KEYS.enterpriseSettings);
        router.refresh();
        toast.success(t("toasts.saved"));
      } catch (e) {
        toast.error(e instanceof Error ? e.message : t("toasts.saveFailed"));
      } finally {
        setSaving(false);
      }
    },
    [router, t]
  );

  useBrandColorPreview(draft?.brand_color, draft?.brand_color_dark);

  if (isLoading && draft === null) {
    return (
      <SettingsLayouts.Root>
        <SettingsLayouts.Header
          icon={route.icon}
          title={adminRouteTitle(route)}
          description={t("header.description")}
          divider
        />
        <SettingsLayouts.Body>
          <Text font="main-ui-body" color="text-04">
            {t("actions.loading")}
          </Text>
        </SettingsLayouts.Body>
      </SettingsLayouts.Root>
    );
  }

  if (!draft) {
    return (
      <SettingsLayouts.Root>
        <SettingsLayouts.Header
          icon={route.icon}
          title={adminRouteTitle(route)}
          description={t("header.description")}
          divider
        />
        <SettingsLayouts.Body>
          <Text font="main-ui-body" color="text-04">
            {t("loadFailed")}
          </Text>
        </SettingsLayouts.Body>
      </SettingsLayouts.Root>
    );
  }

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        description={t("header.description")}
        divider
      />

      <SettingsLayouts.Body>
        {/* ── Application identity ─────────────────────────────────── */}
        <Card border="solid" rounding={4}>
          <Section alignItems="stretch">
            <Text font="heading-h3">{t("identity.title")}</Text>
            <InputVertical
              title={t("identity.appName.title")}
              description={t("identity.appName.description")}
              withLabel
            >
              <div className="flex items-center gap-2 w-full">
                <div className="flex-1">
                  <InputTypeIn
                    value={draft.application_name ?? ""}
                    placeholder={t("identity.appName.placeholder")}
                    onChange={(e) =>
                      updateDraft({ application_name: e.target.value || null })
                    }
                  />
                </div>
                <Button
                  prominence="primary"
                  disabled={saving}
                  onClick={() =>
                    void saveFields({
                      application_name: draft.application_name,
                    })
                  }
                >
                  {t("actions.save")}
                </Button>
              </div>
            </InputVertical>

            <InputHorizontal
              title={t("identity.displayStyle.title")}
              description={t("identity.displayStyle.description")}
              withLabel
            >
              <InputSelect
                value={draft.logo_display_style ?? "logo_and_name"}
                onValueChange={(value) => {
                  // SAFETY: the only items rendered are LOGO_DISPLAY_STYLES
                  // members, so the string value is a LogoDisplayStyle.
                  const style = value as LogoDisplayStyle;
                  updateDraft({ logo_display_style: style });
                  void saveFields({ logo_display_style: style });
                }}
              >
                <InputSelect.Trigger
                  placeholder={t("identity.displayStyle.placeholder")}
                >
                  {t(
                    `identity.displayStyle.options.${
                      draft.logo_display_style ?? "logo_and_name"
                    }`
                  )}
                </InputSelect.Trigger>
                <InputSelect.Content>
                  {LOGO_DISPLAY_STYLES.map((style) => (
                    <InputSelect.Item key={style} value={style}>
                      {t(`identity.displayStyle.options.${style}`)}
                    </InputSelect.Item>
                  ))}
                </InputSelect.Content>
              </InputSelect>
            </InputHorizontal>

            <InputHorizontal
              title={t("identity.hideBranding.title")}
              description={t("identity.hideBranding.description")}
              withLabel
            >
              <Switch
                checked={draft.hide_onyx_branding ?? false}
                onCheckedChange={(checked) => {
                  updateDraft({ hide_onyx_branding: checked });
                  void saveFields({ hide_onyx_branding: checked });
                }}
              />
            </InputHorizontal>
          </Section>
        </Card>

        {/* ── Brand assets ─────────────────────────────────────────── */}
        <Card border="solid" rounding={4}>
          <Section alignItems="stretch">
            <Text font="heading-h3">{t("assets.title")}</Text>
            <div className="grid grid-cols-1 gap-y-6">
              <AssetField
                title={t("assets.logo.title")}
                description={t("assets.logo.description")}
                currentFlag={draft.use_custom_logo}
                slot="logo"
                onUploaded={() => updateDraft({ use_custom_logo: true })}
                onRemoved={() => updateDraft({ use_custom_logo: false })}
              />
              <AssetField
                title={t("assets.logoDark.title")}
                description={t("assets.logoDark.description")}
                currentFlag={draft.use_custom_logo_dark}
                slot="logo-dark"
                onUploaded={() => updateDraft({ use_custom_logo_dark: true })}
                onRemoved={() => updateDraft({ use_custom_logo_dark: false })}
              />
              <AssetField
                title={t("assets.logotype.title")}
                description={t("assets.logotype.description")}
                currentFlag={draft.use_custom_logotype}
                slot="logotype"
                rectangular
                onUploaded={() => updateDraft({ use_custom_logotype: true })}
                onRemoved={() => updateDraft({ use_custom_logotype: false })}
              />
              <AssetField
                title={t("assets.logotypeDark.title")}
                description={t("assets.logotypeDark.description")}
                currentFlag={draft.use_custom_logotype_dark}
                slot="logotype-dark"
                rectangular
                onUploaded={() =>
                  updateDraft({ use_custom_logotype_dark: true })
                }
                onRemoved={() =>
                  updateDraft({ use_custom_logotype_dark: false })
                }
              />
              <AssetField
                title={t("assets.favicon.title")}
                description={t("assets.favicon.description")}
                currentFlag={draft.use_custom_favicon}
                slot="favicon"
                onUploaded={() => updateDraft({ use_custom_favicon: true })}
                onRemoved={() => updateDraft({ use_custom_favicon: false })}
              />
            </div>
          </Section>
        </Card>

        {/* ── Theme colors ─────────────────────────────────────────── */}
        <Card border="solid" rounding={4}>
          <Section alignItems="stretch">
            <Text font="heading-h3">{t("theme.title")}</Text>
            <Text font="secondary-body" color="text-03">
              {t("theme.description")}
            </Text>
            <ColorField
              title={t("theme.brandColor.title")}
              description={t("theme.brandColor.description")}
              value={draft.brand_color ?? null}
              onChange={(value) => updateDraft({ brand_color: value })}
            />
            <ColorField
              title={t("theme.brandColorDark.title")}
              description={t("theme.brandColorDark.description")}
              value={draft.brand_color_dark ?? null}
              onChange={(value) => updateDraft({ brand_color_dark: value })}
            />
            <ColorField
              title={t("theme.emailCta.title")}
              description={t("theme.emailCta.description")}
              value={draft.email_cta_color ?? null}
              onChange={(value) => updateDraft({ email_cta_color: value })}
            />
            <div className="flex justify-end">
              <Button
                prominence="primary"
                disabled={saving}
                onClick={() =>
                  void saveFields({
                    brand_color: draft.brand_color,
                    brand_color_dark: draft.brand_color_dark,
                    email_cta_color: draft.email_cta_color,
                  })
                }
              >
                {t("actions.save")}
              </Button>
            </div>
          </Section>
        </Card>

        {/* ── Custom text surfaces ─────────────────────────────────── */}
        <Card border="solid" rounding={4}>
          <Section alignItems="stretch">
            <Text font="heading-h3">{t("copy.title")}</Text>
            <InputVertical
              title={t("copy.greeting.title")}
              description={t("copy.greeting.description")}
              withLabel
            >
              <InputTypeIn
                value={draft.custom_greeting_message ?? ""}
                onChange={(e) =>
                  updateDraft({
                    custom_greeting_message: e.target.value || null,
                  })
                }
              />
            </InputVertical>
            <InputVertical
              title={t("copy.loginSubtitle.title")}
              description={t("copy.loginSubtitle.description")}
              withLabel
            >
              <InputTypeIn
                value={draft.custom_login_subtitle ?? ""}
                onChange={(e) =>
                  updateDraft({ custom_login_subtitle: e.target.value || null })
                }
              />
            </InputVertical>
            <InputVertical
              title={t("copy.chatHeader.title")}
              description={t("copy.chatHeader.description")}
              withLabel
            >
              <InputTextArea
                value={draft.custom_header_content ?? ""}
                onChange={(e) =>
                  updateDraft({ custom_header_content: e.target.value || null })
                }
              />
            </InputVertical>
            <InputVertical
              title={t("copy.disclaimer.title")}
              description={t("copy.disclaimer.description")}
              withLabel
            >
              <InputTextArea
                value={draft.custom_lower_disclaimer_content ?? ""}
                onChange={(e) =>
                  updateDraft({
                    custom_lower_disclaimer_content: e.target.value || null,
                  })
                }
              />
            </InputVertical>
            <div className="grid grid-cols-2 gap-4">
              <InputVertical title={t("copy.helpLinkLabel.title")} withLabel>
                <InputTypeIn
                  value={draft.custom_help_link_label ?? ""}
                  onChange={(e) =>
                    updateDraft({
                      custom_help_link_label: e.target.value || null,
                    })
                  }
                />
              </InputVertical>
              <InputVertical title={t("copy.helpLinkUrl.title")} withLabel>
                <InputTypeIn
                  value={draft.custom_help_link_url ?? ""}
                  placeholder="https://"
                  onChange={(e) =>
                    updateDraft({
                      custom_help_link_url: e.target.value || null,
                    })
                  }
                />
              </InputVertical>
            </div>
            <div className="flex justify-end">
              <Button
                prominence="primary"
                disabled={saving}
                onClick={() =>
                  void saveFields({
                    custom_greeting_message: draft.custom_greeting_message,
                    custom_login_subtitle: draft.custom_login_subtitle,
                    custom_header_content: draft.custom_header_content,
                    custom_lower_disclaimer_content:
                      draft.custom_lower_disclaimer_content,
                    custom_help_link_label: draft.custom_help_link_label,
                    custom_help_link_url: draft.custom_help_link_url,
                  })
                }
              >
                {t("actions.save")}
              </Button>
            </div>
          </Section>
        </Card>

        {/* ── Custom navigation ────────────────────────────────────── */}
        <Card border="solid" rounding={4}>
          <Section alignItems="stretch">
            <Text font="heading-h3">{t("nav.title")}</Text>
            <Text font="secondary-body" color="text-03">
              {t("nav.description")}
            </Text>
            {(draft.custom_nav_items ?? []).map((item, index) => (
              <div key={index} className="flex items-center gap-2 w-full">
                <InputTypeIn
                  value={item.title}
                  placeholder={t("nav.itemTitlePlaceholder")}
                  onChange={(e) => {
                    const items = [...(draft.custom_nav_items ?? [])];
                    const current = items[index];
                    if (!current) return;
                    items[index] = { ...current, title: e.target.value };
                    updateDraft({ custom_nav_items: items });
                  }}
                />
                <InputTypeIn
                  value={item.link}
                  placeholder="https://"
                  onChange={(e) => {
                    const items = [...(draft.custom_nav_items ?? [])];
                    const current = items[index];
                    if (!current) return;
                    items[index] = { ...current, link: e.target.value };
                    updateDraft({ custom_nav_items: items });
                  }}
                />
                <Button
                  prominence="tertiary"
                  icon={SvgX}
                  onClick={() => {
                    const items = (draft.custom_nav_items ?? []).filter(
                      (_, i) => i !== index
                    );
                    updateDraft({ custom_nav_items: items });
                  }}
                />
              </div>
            ))}
            <div className="flex items-center justify-between w-full">
              <Button
                prominence="secondary"
                icon={SvgAddLines}
                onClick={() =>
                  updateDraft({
                    custom_nav_items: [
                      ...(draft.custom_nav_items ?? []),
                      { title: "", link: "" },
                    ],
                  })
                }
              >
                {t("nav.addItem")}
              </Button>
              <Button
                prominence="primary"
                disabled={saving}
                onClick={() =>
                  void saveFields({
                    custom_nav_items: (draft.custom_nav_items ?? []).filter(
                      (item) => item.title.trim() && item.link.trim()
                    ),
                  })
                }
              >
                {t("actions.save")}
              </Button>
            </div>
            <Divider />
          </Section>
        </Card>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
