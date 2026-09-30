"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import { useSWRConfig } from "swr";
import { useFormikContext } from "formik";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputTypeInField from "@/refresh-components/form/InputTypeInField";
import { Section } from "@/layouts/general-layouts";
import { InputDivider, InputPadder, InputVertical, toast } from "@opal/layouts";
import * as Yup from "yup";
import {
  LLMProviderFormProps,
  LLMProviderName,
  LLMProviderView,
} from "@/lib/languageModels/types";
import {
  DASHSCOPE_CUSTOM_REGION,
  DASHSCOPE_REGIONS,
  composeDashscopeBase,
  parseDashscopeBase,
} from "@/lib/languageModels/dashscope";
import { fetchDashscopeModels } from "@/lib/languageModels/svc";
import {
  useInitialValues,
  buildValidationSchema,
  BaseLLMFormValues,
  withFetchedModels,
} from "@/sections/modals/languageModels/utils";
import { submitProvider } from "@/sections/modals/languageModels/svc";
import { LLMProviderConfiguredSource } from "@/lib/analytics/utils";
import {
  APIKeyField,
  ModelSelectionField,
  DisplayNameField,
  ModelAccessField,
  ModalWrapper,
} from "@/sections/modals/languageModels/shared";
import { refreshLlmProviderCaches } from "@/lib/languageModels/cache";

const FIELD_WORKSPACE_ID = "workspace_id";
const FIELD_REGION = "region";
const FIELD_CUSTOM_API_BASE = "custom_api_base";

interface DashscopeModalValues extends BaseLLMFormValues {
  api_key: string;
  workspace_id: string;
  region: string;
  custom_api_base: string;
}

interface DashscopeModalInternalsProps {
  existingLlmProvider: LLMProviderView | undefined;
  isOnboarding: boolean;
}

function DashscopeModalInternals({
  existingLlmProvider,
  isOnboarding,
}: DashscopeModalInternalsProps) {
  const t = useTranslations("admin.languageModels.modals");
  const formikProps = useFormikContext<DashscopeModalValues>();
  const { setValues, values } = formikProps;

  const isCustomRegion = values.region === DASHSCOPE_CUSTOM_REGION;
  const composedApiBase = composeDashscopeBase(
    values.workspace_id,
    values.region,
    values.custom_api_base
  );
  const canFetchModels =
    !!values.api_key &&
    (isCustomRegion ? values.custom_api_base.trim() !== "" : true);

  const handleFetchModels = async () => {
    const { models, error } = await fetchDashscopeModels({
      api_base: composedApiBase,
      api_key: values.api_key || undefined,
      provider_id: existingLlmProvider?.id ?? undefined,
    });
    if (error) {
      throw new Error(error);
    }
    setValues(withFetchedModels(models));
  };

  // Refetch once on open so an edit's picker matches the "add" view. Best
  // effort: ignore errors so the modal still works if the key is unreachable.
  const autoRefetched = useRef(false);
  useEffect(() => {
    if (autoRefetched.current || !existingLlmProvider?.id) return;
    if (!values.api_key) return;
    autoRefetched.current = true;
    fetchDashscopeModels({
      api_base: composedApiBase,
      api_key: values.api_key || undefined,
      provider_id: existingLlmProvider.id,
    })
      .then(({ models }) => {
        if (models.length > 0) {
          setValues(withFetchedModels(models));
        }
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <InputPadder>
        <Section gap={4}>
          <InputVertical
            withLabel={FIELD_REGION}
            title={t("dashscope.regionField.title")}
            subDescription={t("dashscope.regionField.description")}
          >
            <InputSelect
              value={values.region}
              onValueChange={(value) =>
                formikProps.setFieldValue(FIELD_REGION, value)
              }
            >
              <InputSelect.Trigger />
              <InputSelect.Content>
                {DASHSCOPE_REGIONS.map((region) => (
                  <InputSelect.Item
                    key={region.code}
                    value={region.code}
                    description={region.code}
                  >
                    {region.label}
                  </InputSelect.Item>
                ))}
                <InputSelect.Separator />
                <InputSelect.Item
                  value={DASHSCOPE_CUSTOM_REGION}
                  description={t("dashscope.regionField.custom.description")}
                >
                  {t("dashscope.regionField.custom.label")}
                </InputSelect.Item>
              </InputSelect.Content>
            </InputSelect>
          </InputVertical>

          {!isCustomRegion && (
            <InputVertical
              withLabel={FIELD_WORKSPACE_ID}
              title={t("dashscope.workspaceIdField.title")}
              subDescription={t("dashscope.workspaceIdField.description")}
            >
              <InputTypeInField
                name={FIELD_WORKSPACE_ID}
                placeholder="your-workspace-id"
              />
            </InputVertical>
          )}

          {isCustomRegion && (
            <InputVertical
              withLabel={FIELD_CUSTOM_API_BASE}
              title={t("dashscope.customBaseField.title")}
              subDescription={t("dashscope.customBaseField.description")}
            >
              <InputTypeInField
                name={FIELD_CUSTOM_API_BASE}
                placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
              />
            </InputVertical>
          )}
        </Section>
      </InputPadder>

      <APIKeyField
        subDescription={t("dashscope.apiKeyField.description")}
      />

      {!isOnboarding && (
        <>
          <InputDivider />
          <DisplayNameField />
        </>
      )}

      <InputDivider />
      <ModelSelectionField
        shouldShowAutoUpdateToggle={false}
        onRefetch={canFetchModels ? handleFetchModels : undefined}
      />

      {!isOnboarding && (
        <>
          <InputDivider />
          <ModelAccessField />
        </>
      )}
    </>
  );
}

export default function DashscopeModal({
  variant = "llm-configuration",
  existingLlmProvider,
  shouldMarkAsDefault,
  onOpenChange,
  onSuccess,
  analyticsSource,
}: LLMProviderFormProps) {
  const t = useTranslations("admin.languageModels.modals");
  const isOnboarding = variant === "onboarding";
  const { mutate } = useSWRConfig();

  const onClose = () => onOpenChange?.(false);

  const parsedBase = parseDashscopeBase(existingLlmProvider?.api_base);
  // SAFETY: useInitialValues returns the shared base fields; the three
  // dashscope-specific fields are always set below, so this cast only widens.
  const initialValues: DashscopeModalValues = {
    ...useInitialValues(
      isOnboarding,
      LLMProviderName.DASHSCOPE,
      existingLlmProvider
    ),
    workspace_id: parsedBase.workspaceId,
    region: parsedBase.region,
    custom_api_base: parsedBase.customBase,
  } as DashscopeModalValues;

  const validationSchema = buildValidationSchema(t, isOnboarding, {
    apiKey: true,
    extra: {
      region: Yup.string().required(t("dashscope.validation.regionRequired")),
      workspace_id: Yup.string().when("region", {
        is: (region: string) => region !== DASHSCOPE_CUSTOM_REGION,
        then: (schema) =>
          schema.required(t("dashscope.validation.workspaceIdRequired")),
        otherwise: (schema) => schema.notRequired(),
      }),
      custom_api_base: Yup.string().when("region", {
        is: DASHSCOPE_CUSTOM_REGION,
        then: (schema) =>
          schema.required(t("dashscope.validation.customBaseRequired")),
        otherwise: (schema) => schema.notRequired(),
      }),
    },
  });

  return (
    <ModalWrapper
      providerName={LLMProviderName.DASHSCOPE}
      llmProvider={existingLlmProvider}
      onClose={onClose}
      description={t("dashscope.description")}
      initialValues={initialValues}
      validationSchema={validationSchema}
      onSubmit={async (values, { setSubmitting, setStatus }) => {
        // The workspace/region fields exist only for this form; the composed
        // endpoint is what gets stored and sent to the backend.
        const { workspace_id, region, custom_api_base, ...base } = values;
        await submitProvider({
          t,
          analyticsSource:
            analyticsSource ??
            (isOnboarding
              ? LLMProviderConfiguredSource.CHAT_ONBOARDING
              : LLMProviderConfiguredSource.ADMIN_PAGE),
          providerName: LLMProviderName.DASHSCOPE,
          values: {
            ...base,
            api_base: composeDashscopeBase(
              workspace_id,
              region,
              custom_api_base
            ),
          },
          initialValues,
          existingLlmProvider,
          shouldMarkAsDefault,
          setStatus,
          setSubmitting,
          onClose,
          onSuccess: async () => {
            if (onSuccess) {
              await onSuccess();
            } else {
              await refreshLlmProviderCaches(mutate);
              toast.success(
                existingLlmProvider
                  ? t("toasts.providerUpdated")
                  : t("toasts.providerEnabled")
              );
            }
          },
        });
      }}
    >
      <DashscopeModalInternals
        existingLlmProvider={existingLlmProvider}
        isOnboarding={isOnboarding}
      />
    </ModalWrapper>
  );
}
