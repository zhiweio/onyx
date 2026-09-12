"use client";

import { LLMProviderFormProps, LLMProviderName } from "@/lib/languageModels/types";
import ApiKeyProviderModal from "@/sections/modals/languageModels/ApiKeyProviderModal";

export default function KimiModal(props: LLMProviderFormProps) {
  return (
    <ApiKeyProviderModal
      {...props}
      providerName={LLMProviderName.MOONSHOT}
      apiKeyLabel="Moonshot"
    />
  );
}
