import { createRef } from "react";
import { act, fireEvent, screen } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import BaseInputBar, {
  type BaseInputBarHandle,
} from "@/sections/input/BaseInputBar";

describe("BaseInputBar primary action", () => {
  it("uses one stop control while a turn is running", () => {
    const onInterrupt = jest.fn();
    const onSubmit = jest.fn();

    render(
      <BaseInputBar
        onSubmit={onSubmit}
        isRunning
        onInterrupt={onInterrupt}
        onQueueMessage={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Stop generating" }));

    expect(onInterrupt).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "Send" })
    ).not.toBeInTheDocument();
  });

  it("switches the same control to queue when a follow-up is drafted", () => {
    const onInterrupt = jest.fn();
    const onQueueMessage = jest.fn();
    const ref = createRef<BaseInputBarHandle>();

    render(
      <BaseInputBar
        ref={ref}
        onSubmit={jest.fn()}
        isRunning
        onInterrupt={onInterrupt}
        onQueueMessage={onQueueMessage}
      />
    );

    act(() => {
      ref.current?.setMessage("follow up");
    });

    fireEvent.click(screen.getByRole("button", { name: "Queue message" }));

    expect(onQueueMessage).toHaveBeenCalledWith("follow up");
    expect(onInterrupt).not.toHaveBeenCalled();
  });
});
