"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useFocusOnMount } from "@opal/hooks";
import { Formik, Form, type FormikProps } from "formik";
import * as Yup from "yup";
import { Modal } from "@opal/components";
import { Content, InputVertical, toast } from "@opal/layouts";
import InputTypeInField from "@/refresh-components/form/InputTypeInField";
import InputTextAreaField from "@/refresh-components/form/InputTextAreaField";
import {
  createMCPServer,
  createMCPServerFromPack,
  updateMCPServer,
} from "@/lib/tools/svc";
import type { McpSurface } from "@/lib/tools/mcpSurface";
import {
  MCPServerCreateRequest,
  MCPServerStatus,
  MCPServer,
} from "@/lib/tools/types";
import { useModal } from "@opal/components";
import { useUser } from "@/providers/UserProvider";
import { hasPermission } from "@/lib/permissions";
import { Permission } from "@/lib/types";
import {
  Button,
  Checkbox,
  Divider,
  InputTypeIn,
  LineItemButton,
  Tabs,
  Text,
} from "@opal/components";
import type { ModalCreationInterface } from "@opal/components";
import {
  SvgBlocks,
  SvgCheckCircle,
  SvgLink,
  SvgServer,
  SvgUnplug,
} from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import { IsPublicGroupSelector } from "@/components/IsPublicGroupSelector";
import { useSettings } from "@/lib/settings/hooks";
import { listMcpPacks } from "@/lib/mcp-catalog/api";
import type { McpPack } from "@/lib/mcp-catalog/types";

interface AddMCPServerModalProps {
  skipOverlay?: boolean;
  activeServer: MCPServer | null;
  setActiveServer: (server: MCPServer | null) => void;
  disconnectModal: ModalCreationInterface;
  manageServerModal: ModalCreationInterface;
  onServerCreated?: (server: MCPServer) => void;
  handleAuthenticate: (serverId: number) => void;
  mutateMcpServers?: () => Promise<void>;
  surface?: McpSurface;
}

type InstallMode = "custom" | "pack";

const PACK_GROUP_ORDER = ["common", "enterprise", "generic"] as const;
const PACK_COPY_SLUGS = [
  "context7",
  "deepwiki",
  "microsoft_learn",
  "parallel_search",
  "patsnap",
  "qixinbao",
  "tianyancha",
  "generic_http",
] as const;

type PackCopySlug = (typeof PACK_COPY_SLUGS)[number];
type PackGroup = (typeof PACK_GROUP_ORDER)[number];

function isPackCopySlug(slug: string): slug is PackCopySlug {
  return PACK_COPY_SLUGS.some((item) => item === slug);
}

function packNeedsUrl(pack: McpPack | null): boolean {
  return pack !== null && !pack.default_upstream_url;
}

export default function AddMCPServerModal({
  skipOverlay = false,
  activeServer,
  disconnectModal,
  manageServerModal,
  onServerCreated,
  handleAuthenticate,
  mutateMcpServers,
  surface = "admin",
}: AddMCPServerModalProps) {
  const t = useTranslations("actions");
  const { isOpen, toggle } = useModal();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [installMode, setInstallMode] = useState<InstallMode>("custom");
  const [packs, setPacks] = useState<McpPack[]>([]);
  const [packsLoading, setPacksLoading] = useState(false);
  const [selectedPackSlug, setSelectedPackSlug] = useState<string | null>(null);
  const [routeThroughGateway, setRouteThroughGateway] = useState(false);
  const [gatewaySlug, setGatewaySlug] = useState("");
  const [packApiKey, setPackApiKey] = useState("");
  const focusOnMount = useFocusOnMount<HTMLInputElement>();

  const { permissions } = useUser();
  const settings = useSettings();
  const gatewayReady =
    surface === "admin" &&
    settings.mcp_gateway_available === true &&
    settings.mcp_gateway_enabled === true;

  const selectedPack = useMemo(
    () => packs.find((pack) => pack.slug === selectedPackSlug) ?? null,
    [packs, selectedPackSlug]
  );

  useEffect(() => {
    if (!isOpen) return;
    setInstallMode("custom");
    setSelectedPackSlug(null);
    setRouteThroughGateway(false);
    setGatewaySlug("");
    setPackApiKey("");
  }, [isOpen]);

  useEffect(() => {
    if (!gatewayReady || !isOpen) return;
    setPacksLoading(true);
    void listMcpPacks()
      .then(setPacks)
      .catch(() => setPacks([]))
      .finally(() => setPacksLoading(false));
  }, [gatewayReady, isOpen]);

  const validationSchema = useMemo(
    () =>
      Yup.object().shape({
        name: Yup.string().required(t("addMcpModal.name.required")),
        description: Yup.string(),
        server_url:
          installMode === "pack" && !packNeedsUrl(selectedPack)
            ? Yup.string()
            : Yup.string()
                .url(t("addMcpModal.serverUrl.invalid"))
                .required(t("addMcpModal.serverUrl.required")),
      }),
    [installMode, selectedPack, t]
  );

  const server = activeServer;

  const handleDisconnectClick = () => {
    if (activeServer) {
      manageServerModal.toggle(false);
      disconnectModal.toggle(true);
    }
  };

  const isEditMode = !!server;

  const initialValues: MCPServerCreateRequest = {
    name: server?.name || "",
    description: server?.description || "",
    server_url: server?.server_url || "",
    is_public: server?.is_public ?? true,
    groups: server?.groups ?? [],
    users: server?.users ?? [],
  };

  const packDescription = (pack: McpPack): string => {
    if (isPackCopySlug(pack.slug)) {
      return t(`addMcpModal.packs.${pack.slug}`);
    }
    return pack.description;
  };

  const applyPack = (
    pack: McpPack,
    formikProps: FormikProps<MCPServerCreateRequest>
  ) => {
    setSelectedPackSlug(pack.slug);
    void formikProps.setValues({
      ...formikProps.values,
      name: pack.display_name,
      description: packDescription(pack),
      server_url: pack.default_upstream_url || "",
    });
    setPackApiKey("");
    setGatewaySlug("");
  };

  const handleSubmit = async (values: MCPServerCreateRequest) => {
    setIsSubmitting(true);

    const access = {
      is_public: values.is_public,
      groups: values.is_public ? [] : values.groups,
      users: values.is_public ? [] : values.users,
    };

    try {
      if (isEditMode && server) {
        await updateMCPServer(server.id, { ...values, ...access }, surface);
        toast.success(t("addMcpModal.toasts.serverUpdated"));
        await mutateMcpServers?.();
      } else if (installMode === "pack" && selectedPack) {
        const createdServer = await createMCPServerFromPack({
          pack_slug: selectedPack.slug,
          name: values.name,
          slug: gatewaySlug || undefined,
          description: values.description,
          upstream_url: values.server_url || undefined,
          credentials: packApiKey ? { api_key: packApiKey } : {},
          ...access,
        });
        toast.success(t("addMcpModal.toasts.serverCreated"));
        await mutateMcpServers?.();
        onServerCreated?.(createdServer);
      } else {
        const payload: MCPServerCreateRequest = {
          ...values,
          ...access,
          gateway_binding:
            gatewayReady && routeThroughGateway
              ? {
                  slug: gatewaySlug || undefined,
                  pack_slug: "generic_http",
                  upstream_url: values.server_url,
                }
              : undefined,
        };
        const createdServer = await createMCPServer(payload, surface);
        toast.success(t("addMcpModal.toasts.serverCreated"));
        await mutateMcpServers?.();
        onServerCreated?.(createdServer);
      }
      toggle(false);
    } catch (error) {
      console.error(
        `Error ${isEditMode ? "updating" : "creating"} MCP server:`,
        error
      );
      toast.error(
        error instanceof Error
          ? error.message
          : isEditMode
            ? t("addMcpModal.toasts.updateFailed")
            : t("addMcpModal.toasts.createFailed")
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleModalClose = (open: boolean) => {
    toggle(open);
  };

  const showInstallModes = gatewayReady && !isEditMode;
  const showPackFields = installMode !== "pack" || selectedPack !== null;
  const showUrlField =
    showPackFields && (installMode !== "pack" || packNeedsUrl(selectedPack));
  const packReady = installMode !== "pack" || selectedPack !== null;

  return (
    <Modal open={isOpen} onOpenChange={handleModalClose}>
      <Modal.Content
        width={showInstallModes && installMode === "pack" ? "lg" : showInstallModes ? "md" : "sm"}
        height={showInstallModes && installMode === "pack" ? "lg" : "fit"}
        preventAccidentalClose={false}
        skipOverlay={skipOverlay}
      >
        <Formik
          initialValues={initialValues}
          validationSchema={validationSchema}
          onSubmit={handleSubmit}
          enableReinitialize
        >
          {(formikProps) => (
            <Form>
              <Modal.Header
                icon={SvgServer}
                title={
                  isEditMode
                    ? t("addMcpModal.manageHeader.title")
                    : t("addMcpModal.addHeader.title")
                }
                description={
                  isEditMode
                    ? t("addMcpModal.manageHeader.description")
                    : t("addMcpModal.addHeader.description")
                }
                onClose={() => handleModalClose(false)}
              />

              <Modal.Body>
                {showInstallModes && (
                  <Tabs
                    value={installMode}
                    onValueChange={(value) => {
                      if (value !== "custom" && value !== "pack") return;
                      setInstallMode(value);
                      if (value === "custom") {
                        setSelectedPackSlug(null);
                        return;
                      }
                      void formikProps.setFieldValue("server_url", "");
                    }}
                  >
                    <Tabs.List>
                      <Tabs.Trigger
                        value="custom"
                        icon={SvgLink}
                        data-testid="mcp-install-custom"
                      >
                        {t("addMcpModal.installMode.custom")}
                      </Tabs.Trigger>
                      <Tabs.Trigger
                        value="pack"
                        icon={SvgBlocks}
                        data-testid="mcp-install-pack"
                      >
                        {t("addMcpModal.installMode.pack")}
                      </Tabs.Trigger>
                    </Tabs.List>
                  </Tabs>
                )}

                {showInstallModes && installMode === "pack" && (
                  <Section gap={3} alignItems="start" width="full">
                    <Text font="secondary-body" color="text-03" as="p">
                      {t("addMcpModal.packHint")}
                    </Text>
                    {packsLoading ? (
                      <Text font="secondary-body" color="text-03" as="p">
                        {t("addMcpModal.packList.loading")}
                      </Text>
                    ) : packs.length === 0 ? (
                      <Text font="secondary-body" color="text-03" as="p">
                        {t("addMcpModal.packList.empty")}
                      </Text>
                    ) : selectedPack ? (
                      <Section
                        flexDirection="row"
                        alignItems="center"
                        gap={2}
                        width="full"
                      >
                        <div
                          className="min-w-0 flex-1 rounded-12 border border-border-03 bg-background-tint-00 p-3"
                          data-testid={`mcp-pack-${selectedPack.slug}`}
                        >
                          <Content
                            sizePreset="main-ui"
                            variant="section"
                            title={selectedPack.display_name}
                            description={packDescription(selectedPack)}
                          />
                        </div>
                        <Button
                          type="button"
                          prominence="secondary"
                          data-testid="mcp-pack-change"
                          onClick={() => setSelectedPackSlug(null)}
                        >
                          {t("addMcpModal.packList.change")}
                        </Button>
                      </Section>
                    ) : (
                      <>
                        <div className="flex w-full max-h-[28rem] flex-col gap-4 overflow-y-auto pr-1">
                          {PACK_GROUP_ORDER.map((group: PackGroup) => {
                            const groupPacks = packs.filter(
                              (pack) => (pack.group ?? "generic") === group
                            );
                            if (groupPacks.length === 0) return null;
                            return (
                              <div
                                key={group}
                                className="flex w-full flex-col gap-2"
                              >
                                <Text
                                  font="secondary-action"
                                  color="text-03"
                                  as="p"
                                >
                                  {t(`addMcpModal.packGroup.${group}`)}
                                </Text>
                                <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
                                  {groupPacks.map((pack) => (
                                    <div
                                      key={pack.slug}
                                      data-testid={`mcp-pack-${pack.slug}`}
                                    >
                                      <LineItemButton
                                        selectVariant="select-heavy"
                                        state="empty"
                                        rounding={3}
                                        onClick={() =>
                                          applyPack(pack, formikProps)
                                        }
                                        title={pack.display_name}
                                        description={packDescription(pack)}
                                        sizePreset="main-ui"
                                        variant="section"
                                      />
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        <Text font="secondary-body" color="text-03" as="p">
                          {t("addMcpModal.packList.prompt")}
                        </Text>
                      </>
                    )}
                  </Section>
                )}

                {showPackFields && (
                  <>
                    <InputVertical
                      withLabel="name"
                      title={t("addMcpModal.name.title")}
                    >
                      <InputTypeInField
                        name="name"
                        placeholder={t("addMcpModal.name.placeholder")}
                        ref={focusOnMount}
                      />
                    </InputVertical>

                    <InputVertical
                      withLabel="description"
                      title={t("addMcpModal.description.title")}
                      suffix={t("addMcpModal.description.suffix")}
                    >
                      <InputTextAreaField
                        name="description"
                        placeholder={t("addMcpModal.description.placeholder")}
                        rows={3}
                      />
                    </InputVertical>

                    <Divider paddingParallel={0} paddingPerpendicular={0} />
                  </>
                )}

                {showUrlField && (
                  <InputVertical
                    withLabel="server_url"
                    title={t("addMcpModal.serverUrl.title")}
                    subDescription={t("addMcpModal.serverUrl.subDescription")}
                  >
                    <InputTypeInField
                      name="server_url"
                      placeholder="https://your-mcp-server.com/mcp"
                    />
                  </InputVertical>
                )}

                {showInstallModes && installMode === "custom" && (
                  <div className="flex w-full flex-col gap-3 rounded-12 border border-border-01 p-3">
                    <div className="flex items-start gap-2">
                      <Checkbox
                        checked={routeThroughGateway}
                        onCheckedChange={(checked) =>
                          setRouteThroughGateway(checked === true)
                        }
                        aria-label={t("addMcpModal.routeThrough.title")}
                      />
                      <div
                        className="flex cursor-pointer flex-col gap-1"
                        role="presentation"
                        onClick={() =>
                          setRouteThroughGateway((current) => !current)
                        }
                      >
                        <Text font="main-ui-body" color="text-04" as="p">
                          {t("addMcpModal.routeThrough.title")}
                        </Text>
                        <Text font="secondary-body" color="text-03" as="p">
                          {t("addMcpModal.routeThrough.description")}
                        </Text>
                      </div>
                    </div>
                    {routeThroughGateway && (
                      <InputVertical
                        title={t("addMcpModal.slug.title")}
                        suffix={t("addMcpModal.description.suffix")}
                      >
                        <InputTypeIn
                          name="gateway_slug"
                          placeholder={t("addMcpModal.slug.placeholder")}
                          value={gatewaySlug}
                          onChange={(event) =>
                            setGatewaySlug(event.target.value)
                          }
                        />
                      </InputVertical>
                    )}
                  </div>
                )}

                {showInstallModes &&
                  installMode === "pack" &&
                  selectedPack && (
                    <Section gap={3} alignItems="start" width="full">
                      <InputVertical
                        title={t("addMcpModal.packApiKey.title")}
                        suffix={t("addMcpModal.description.suffix")}
                      >
                        <InputTypeIn
                          name="pack_api_key"
                          placeholder={t("addMcpModal.packApiKey.placeholder")}
                          value={packApiKey}
                          onChange={(event) =>
                            setPackApiKey(event.target.value)
                          }
                        />
                      </InputVertical>
                      <InputVertical
                        title={t("addMcpModal.slug.title")}
                        suffix={t("addMcpModal.description.suffix")}
                      >
                        <InputTypeIn
                          name="gateway_slug"
                          placeholder={t("addMcpModal.slug.placeholder")}
                          value={gatewaySlug}
                          onChange={(event) =>
                            setGatewaySlug(event.target.value)
                          }
                        />
                      </InputVertical>
                    </Section>
                  )}

                {showPackFields && (
                  <>
                    <Divider paddingParallel={0} paddingPerpendicular={0} />

                    {surface !== "personal" && (
                      <IsPublicGroupSelector
                        formikProps={formikProps}
                        objectName="MCP server"
                        isGlobalHolder={hasPermission(
                          permissions,
                          Permission.MANAGE_ACTIONS
                        )}
                        publicToWhom="Users"
                      />
                    )}
                  </>
                )}

                {isEditMode &&
                  server?.user_can_authenticate &&
                  server?.status === MCPServerStatus.CONNECTED && (
                    <Section
                      flexDirection="row"
                      justifyContent="between"
                      alignItems="start"
                      gap={4}
                    >
                      <Section gap={1} alignItems="start">
                        <Section
                          flexDirection="row"
                          gap={2}
                          alignItems="center"
                          width="fit"
                        >
                          <SvgCheckCircle className="w-4 h-4 stroke-status-success-05" />
                          <Text font="main-ui-body" color="text-04">
                            {t("addMcpModal.authStatus.title")}
                          </Text>
                        </Section>
                        <Text font="secondary-body" color="text-03">
                          {server.auth_type === "OAUTH"
                            ? t("addMcpModal.authStatus.oauthDescription", {
                                owner: server.owner,
                              })
                            : server.auth_type === "API_TOKEN"
                              ? t("addMcpModal.authStatus.apiTokenDescription")
                              : t(
                                  "addMcpModal.authStatus.connectedDescription"
                                )}
                        </Text>
                      </Section>
                      <Section
                        flexDirection="row"
                        gap={2}
                        alignItems="center"
                        width="fit"
                      >
                        <Button
                          icon={SvgUnplug}
                          prominence="tertiary"
                          type="button"
                          tooltip={t("addMcpModal.disconnectButton.tooltip")}
                          onClick={handleDisconnectClick}
                        />
                        <Button
                          prominence="secondary"
                          type="button"
                          onClick={() => {
                            toggle(false);
                            handleAuthenticate(server.id);
                          }}
                        >
                          {t("addMcpModal.editConfigsButton.label")}
                        </Button>
                      </Section>
                    </Section>
                  )}
              </Modal.Body>

              <Modal.Footer>
                <Button
                  disabled={isSubmitting}
                  prominence="secondary"
                  type="button"
                  onClick={() => handleModalClose(false)}
                >
                  {t("addMcpModal.cancelButton.label")}
                </Button>
                <Button
                  disabled={
                    isSubmitting ||
                    !packReady ||
                    !formikProps.values.name.trim() ||
                    (showUrlField && !formikProps.values.server_url.trim()) ||
                    (!formikProps.dirty &&
                      !(installMode === "pack" && selectedPack))
                  }
                  type="submit"
                >
                  {isSubmitting
                    ? isEditMode
                      ? t("addMcpModal.submitButton.savingLabel")
                      : t("addMcpModal.submitButton.addingLabel")
                    : isEditMode
                      ? t("addMcpModal.submitButton.saveLabel")
                      : t("addMcpModal.submitButton.addLabel")}
                </Button>
              </Modal.Footer>
            </Form>
          )}
        </Formik>
      </Modal.Content>
    </Modal>
  );
}
