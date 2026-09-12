import { craftComposerStopKind } from "@/app/craft/utils/jobInterrupt";

describe("craftComposerStopKind", () => {
  it("cancels the whole long job while lanes are in flight", () => {
    expect(
      craftComposerStopKind({
        jobInFlight: true,
        scheduledRunInFlight: false,
        sessionStatus: "active",
      })
    ).toBe("cancel-job");
  });

  it("still cancels the job when the parent turn is also running", () => {
    expect(
      craftComposerStopKind({
        jobInFlight: true,
        scheduledRunInFlight: false,
        sessionStatus: "running",
      })
    ).toBe("cancel-job");
  });

  it("interrupts a normal parent turn when no job is open", () => {
    expect(
      craftComposerStopKind({
        jobInFlight: false,
        scheduledRunInFlight: false,
        sessionStatus: "running",
      })
    ).toBe("interrupt-turn");
  });

  it("cancels leftover lanes after the job was already marked cancelled", () => {
    expect(
      craftComposerStopKind({
        jobInFlight: true,
        scheduledRunInFlight: false,
        sessionStatus: "active",
      })
    ).toBe("cancel-job");
  });

  it("does not stop a scheduled run from the composer", () => {
    expect(
      craftComposerStopKind({
        jobInFlight: true,
        scheduledRunInFlight: true,
        sessionStatus: "running",
      })
    ).toBeNull();
  });
});
