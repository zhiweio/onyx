import {
  CLOUD_BASED_PROVIDERS,
  findProvider,
  isCloudBased,
} from "@/lib/indexing";
import { EmbeddingProviderName } from "@/lib/indexing/types";

describe("the Alibaba Bailian (DashScope) embedding provider registry entry", () => {
  it("is registered as a cloud provider, resolvable like every other entry", () => {
    expect(isCloudBased(EmbeddingProviderName.DASHSCOPE)).toBe(true);
    expect(
      CLOUD_BASED_PROVIDERS.some(
        (provider) => provider.providerName === EmbeddingProviderName.DASHSCOPE
      )
    ).toBe(true);

    const provider = findProvider(EmbeddingProviderName.DASHSCOPE);
    expect(provider.displayName).toBe("Alibaba Bailian");
  });

  it("registers the v4 and v3 embedding models at their default dimension", () => {
    const provider = findProvider(EmbeddingProviderName.DASHSCOPE);
    const modelNames = provider.embeddingModels.map((model) => model.modelName);

    expect(modelNames).toContain("text-embedding-v4");
    expect(modelNames).toContain("text-embedding-v3");
    for (const model of provider.embeddingModels) {
      // DashScope defaults to 1024 dimensions for both models; the index is
      // built at whatever dim is submitted, so the registry value must match
      // the model's real default.
      expect(model.modelDim).toBe(1024);
      // OpenAI-compatible API: no asymmetric prefixes.
      expect(model.queryPrefix).toBe("");
      expect(model.passagePrefix).toBe("");
    }
  });
});
