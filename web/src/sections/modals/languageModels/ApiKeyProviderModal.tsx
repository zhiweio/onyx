"use client";

import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";
import {
  LLMProviderFormProps,
  LLMProviderName,
} from "@/lib/languageModels/types";
import {
  useInitialValues,
  buildValidationSchema,
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
import { InputDivider, toast } from "@opal/layouts";
import { refreshLlmProviderCaches } from "@/lib/languageModels/cache";

export interface ApiKeyProviderModalProps extends LLMProviderFormProps {
  providerName: LLMProviderName;
  apiKeyLabel: string;
  defaultApiBase?: string;
}

export default function ApiKeyProviderModal({
  providerName,
  apiKeyLabel,
  defaultApiBase,
  variant = "llm-configuration",
  existingLlmProvider,
  shouldMarkAsDefault,
  onOpenChange,
  onSuccess,
  analyticsSource,
}: ApiKeyProviderModalProps) {
  const t = useTranslations("admin.languageModels.modals");
  const isOnboarding = variant === "onboarding";
  const { mutate } = useSWRConfig();

  const onClose = () => onOpenChange?.(false);

  const initialValues = {
    ...useInitialValues(isOnboarding, providerName, existingLlmProvider),
    api_base:
      existingLlmProvider?.api_base ?? defaultApiBase ?? undefined,
  };

  const validationSchema = buildValidationSchema(t, isOnboarding, {
    apiKey: true,
  });

  return (
    <ModalWrapper
      providerName={providerName}
      llmProvider={existingLlmProvider}
      onClose={onClose}
      initialValues={initialValues}
      validationSchema={validationSchema}
      onSubmit={async (values, { setSubmitting, setStatus }) => {
        await submitProvider({
          t,
          analyticsSource:
            analyticsSource ??
            (isOnboarding
              ? LLMProviderConfiguredSource.CHAT_ONBOARDING
              : LLMProviderConfiguredSource.ADMIN_PAGE),
          providerName,
          values,
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
      <APIKeyField providerName={apiKeyLabel} />

      {!isOnboarding && (
        <>
          <InputDivider />
          <DisplayNameField />
        </>
      )}

      <InputDivider />
      <ModelSelectionField shouldShowAutoUpdateToggle={true} />

      {!isOnboarding && (
        <>
          <InputDivider />
          <ModelAccessField />
        </>
      )}
    </ModalWrapper>
  );
}
