/**
 * Playwright global teardown: remove the placeholder LLM provider that
 * global-setup's ensurePublicProvider() may have created ("PW Default
 * Provider" with a non-functional e2e key). Without this, the row persists
 * in the dev database after runs.
 *
 * Idempotent: re-lists by name, so a run that created nothing (or already
 * cleaned) is a no-op. Per-test fixtures (llmProvider.ts) and MCP specs
 * manage their own providers and are intentionally not touched.
 */
import { request } from "@playwright/test";
import { OnyxApiClient } from "@tests/e2e/utils/onyxApiClient";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3000";
const AUTH_STATE = "admin_auth.json";

export async function globalTeardown(): Promise<void> {
  let context: Awaited<ReturnType<typeof request.newContext>> | undefined;
  try {
    context = await request.newContext({
      baseURL: BASE_URL,
      storageState: AUTH_STATE,
    });
    const client = new OnyxApiClient(context, BASE_URL);
    const providers = await client.listLlmProviders();
    const stale = providers.filter((p) => p.name === "PW Default Provider");
    for (const provider of stale) {
      await client.deleteProvider(provider.id, { force: true });
    }
    if (stale.length > 0) {
      console.log(
        `[global-teardown] Removed ${stale.length} stale e2e LLM provider(s)`
      );
    }
  } catch (error) {
    // Teardown must never fail the run; log and move on.
    console.warn(
      "[global-teardown] Provider cleanup skipped:",
      error instanceof Error ? error.message : error
    );
  } finally {
    await context?.dispose();
  }
}

export default globalTeardown;
