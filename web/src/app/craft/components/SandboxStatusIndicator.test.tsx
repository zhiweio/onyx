/**
 * @jest-environment jsdom
 */
import { render, screen } from "@tests/setup/test-utils";
import SandboxStatusIndicator from "@/app/craft/components/SandboxStatusIndicator";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

const SESSION_ID = "11111111-1111-1111-1111-111111111111";

describe("SandboxStatusIndicator", () => {
  beforeEach(() => {
    useBuildSessionStore.setState({
      sessions: new Map(),
      currentSessionId: null,
      preProvisioning: { status: "idle" },
    } as never);
  });

  it("shows a loading state until an existing session has sandbox data", () => {
    useBuildSessionStore.getState().createSession(SESSION_ID);
    useBuildSessionStore.getState().setCurrentSession(SESSION_ID);

    render(<SandboxStatusIndicator />);

    expect(screen.getByText("Finding sandbox...")).toBeInTheDocument();
    expect(screen.queryByText("Sandbox running")).toBeNull();
  });

  it("shows the client-owned restoring state", () => {
    useBuildSessionStore.getState().createSession(SESSION_ID, {
      sandbox: {
        id: "sb1",
        status: "restoring",
        container_id: null,
        created_at: "2026-07-01T00:00:00.000Z",
        last_heartbeat: null,
      },
    });
    useBuildSessionStore.getState().setCurrentSession(SESSION_ID);

    render(<SandboxStatusIndicator />);

    expect(screen.getByText("Restoring session...")).toBeInTheDocument();
  });

  it("shows pre-provisioning readiness before a session is consumed", () => {
    useBuildSessionStore.setState({
      preProvisioning: {
        status: "ready",
        sessionId: SESSION_ID,
      },
    } as never);

    render(<SandboxStatusIndicator />);

    expect(screen.getByText("Sandbox ready")).toBeInTheDocument();
  });
});

it("self-heals a missing sandbox state by refreshing once", async () => {
  jest.useFakeTimers();
  const refresh = jest.fn().mockResolvedValue(undefined);
  useBuildSessionStore.setState({
    refreshSandboxStatus: refresh,
  } as never);
  useBuildSessionStore.getState().createSession(SESSION_ID);
  useBuildSessionStore.getState().setCurrentSession(SESSION_ID);

  render(<SandboxStatusIndicator />);
  expect(refresh).not.toHaveBeenCalled();

  jest.advanceTimersByTime(3100);
  await Promise.resolve();
  await Promise.resolve();

  expect(refresh).toHaveBeenCalledWith(SESSION_ID);
  jest.useRealTimers();
});
