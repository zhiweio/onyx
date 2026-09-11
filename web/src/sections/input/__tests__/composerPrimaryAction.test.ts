import { resolveComposerPrimaryAction } from "@/sections/input/composerPrimaryAction";

describe("resolveComposerPrimaryAction", () => {
  const idle = {
    isRunning: false,
    hasText: false,
    canQueue: false,
    isBusy: false,
    canStop: false,
  };

  it("sends when idle", () => {
    expect(resolveComposerPrimaryAction({ ...idle, hasText: true })).toBe(
      "send"
    );
    expect(resolveComposerPrimaryAction(idle)).toBe("send");
  });

  it("stops when a turn is running and the draft is empty", () => {
    expect(
      resolveComposerPrimaryAction({
        ...idle,
        isRunning: true,
        canStop: true,
      })
    ).toBe("stop");
  });

  it("queues a follow-up when the user types during a run", () => {
    expect(
      resolveComposerPrimaryAction({
        ...idle,
        isRunning: true,
        hasText: true,
        canQueue: true,
        canStop: true,
      })
    ).toBe("queue");
  });

  it("falls back to send when the queue is full", () => {
    expect(
      resolveComposerPrimaryAction({
        ...idle,
        isRunning: true,
        hasText: true,
        canQueue: false,
        canStop: true,
      })
    ).toBe("send");
  });

  it("shows busy ahead of stop or queue", () => {
    expect(
      resolveComposerPrimaryAction({
        ...idle,
        isRunning: true,
        hasText: true,
        canQueue: true,
        canStop: true,
        isBusy: true,
      })
    ).toBe("busy");
  });
});
