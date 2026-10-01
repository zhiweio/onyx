import examplePromptsEn from "@/i18n/messages/en.json";
import { useCaseDomains } from "@/app/craft/constants/exampleBuildPrompts";

/**
 * Every example prompt must carry display copy in the catalog. A missing key
 * renders the raw message id in the UI (the financeTax regression), so pin
 * the full domain/prompt key set against the English catalog — locale parity
 * is enforced separately by the ICU catalog test.
 */
describe("exampleBuildPrompts catalog coverage", () => {
  // SAFETY: the fixture is en.json; only craft.suggestedPrompts is read and
  // its shape is pinned by the assertions below.
  const suggestedPrompts = (
    examplePromptsEn as {
      craft: { suggestedPrompts: Record<string, unknown> };
    }
  ).craft.suggestedPrompts;

  it.each(useCaseDomains)(
    "domain $id has a label and every prompt has summary + fullText",
    (domain) => {
      const domainNode = suggestedPrompts[domain.id] as
        | { label?: unknown; prompts?: Record<string, unknown> }
        | undefined;
      expect(domainNode).toBeDefined();
      const label: unknown = domainNode?.label;
      expect(typeof label).toBe("string");
      // SAFETY: typeof narrowed to string immediately above.
      expect((label as string).length).toBeGreaterThan(0);

      expect(domainNode?.prompts).toBeDefined();
      expect(Object.keys(domainNode?.prompts ?? {})).toHaveLength(
        domain.prompts.length
      );
      for (const prompt of domain.prompts) {
        const promptNode = domainNode?.prompts?.[prompt.id] as
          | { summary?: unknown; fullText?: unknown }
          | undefined;
        expect(promptNode).toBeDefined();
        expect(typeof promptNode?.summary).toBe("string");
        expect(typeof promptNode?.fullText).toBe("string");
      }
    }
  );

  it("keeps the catalog free of extra prompt ids", () => {
    const catalogDomains = Object.keys(suggestedPrompts).filter(
      (key) => key !== "close"
    );
    expect(catalogDomains.sort()).toEqual(
      useCaseDomains.map((domain) => domain.id).sort()
    );
  });
});
