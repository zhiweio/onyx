"use client";

import { LLMProviderFormProps, LLMProviderName } from "@/lib/languageModels/types";
import ApiKeyProviderModal from "@/sections/modals/languageModels/ApiKeyProviderModal";

export default function BigModelModal(props: LLMProviderFormProps) {
  return (
    <ApiKeyProviderModal
      {...props}
      providerName={LLMProviderName.BIGMODEL}
      apiKeyLabel="BigModel"
      defaultApiBase="https://open.bigmodel.cn/api/paas/v4"
    />
  );
}
