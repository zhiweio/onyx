/**
 * @jest-environment jsdom
 */
import { render, screen, setupUser, waitFor, within } from "@tests/setup/test-utils";
import CraftProjectSandboxCard from "@/app/craft/components/CraftProjectSandboxCard";
import type { CraftProjectSandbox } from "@/lib/craft-projects/types";

const RUNNING_SANDBOX: CraftProjectSandbox = {
  id: "sandbox-1",
  status: "running",
  last_heartbeat: "2026-08-01T00:00:00Z",
  created_at: "2026-08-01T00:00:00Z",
};

describe("CraftProjectSandboxCard", () => {
  it("closes the confirm dialog as soon as reset starts", async () => {
    const user = setupUser();
    let finishReset: (() => void) | undefined;
    const onReset = jest.fn(
      () =>
        new Promise<void>((resolve) => {
          finishReset = resolve;
        })
    );

    const { rerender } = render(
      <CraftProjectSandboxCard sandbox={RUNNING_SANDBOX} onReset={onReset} />
    );

    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(
      screen.getByRole("dialog", { name: /Reset the sandbox/ })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();

    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Reset" })
    );

    await waitFor(() => expect(onReset).toHaveBeenCalledWith(false));
    expect(
      screen.queryByRole("dialog", { name: /Reset the sandbox/ })
    ).not.toBeInTheDocument();

    rerender(
      <CraftProjectSandboxCard
        sandbox={RUNNING_SANDBOX}
        resetting
        onReset={onReset}
      />
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Starting a new workspace. You can keep using this page."
    );
    expect(screen.getByRole("button", { name: "Resetting" })).toBeDisabled();

    finishReset?.();
  });

  it("keeps the dialog usable until the user confirms", async () => {
    const user = setupUser();
    const onReset = jest.fn();
    render(
      <CraftProjectSandboxCard sandbox={RUNNING_SANDBOX} onReset={onReset} />
    );

    await user.click(screen.getByRole("button", { name: "Reset" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(
      screen.queryByRole("dialog", { name: /Reset the sandbox/ })
    ).not.toBeInTheDocument();
    expect(onReset).not.toHaveBeenCalled();
  });

  it("passes the output-copy choice after the dialog closes", async () => {
    const user = setupUser();
    const onReset = jest.fn().mockResolvedValue(undefined);
    render(
      <CraftProjectSandboxCard sandbox={RUNNING_SANDBOX} onReset={onReset} />
    );

    await user.click(screen.getByRole("button", { name: "Reset" }));
    await user.click(
      screen.getByRole("checkbox", {
        name: "Also copy every output file from the old sandbox",
      })
    );
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Reset" })
    );

    await waitFor(() => expect(onReset).toHaveBeenCalledWith(true));
    expect(
      screen.queryByRole("dialog", { name: /Reset the sandbox/ })
    ).not.toBeInTheDocument();
  });
});
