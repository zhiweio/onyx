"use client";

import { LLMProviderFormProps, LLMProviderName } from "@/lib/languageModels/types";
import ApiKeyProviderModal from "@/sections/modals/languageModels/ApiKeyProviderModal";

export default function MiniMaxModal(props: LLMProviderFormProps) {
  return (
    <ApiKeyProviderModal
      {...props}
      providerName={LLMProviderName.MINIMAX}
      apiKeyLabel="MiniMax"
    />
  );
}
