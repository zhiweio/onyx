/**
 * Decision-flow coverage for the loop modals: the return-with-note payload
 * and the grant form's validation gate. The list/detail pages themselves are
 * covered by the playwright spec.
 */
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import englishMessages from "@/i18n/messages/en.json";
import ReturnModal from "@/app/craft/v1/loops/components/ReturnModal";
import GrantModal from "@/app/craft/v1/loops/components/GrantModal";
import type { LoopOutput } from "@/app/craft/v1/loops/interfaces";

const output: LoopOutput = {
  id: "out-1",
  item_id: "item-1",
  ship_action: "im_push",
  label: null,
  title: "Weekly risk report",
  summary: "found 3 risks",
  state: "ready",
  decided_by: null,
  decided_at: null,
};

function renderWithIntl(ui: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={englishMessages}>
      {ui}
    </NextIntlClientProvider>
  );
}

describe("ReturnModal", () => {
  const fetchMock = jest.fn();
  const onDecided = jest.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    onDecided.mockReset();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  test("sends decision return with the typed note", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ...output, state: "returned" }), {
        status: 200,
      })
    );

    renderWithIntl(
      <ReturnModal
        loopId="loop-1"
        output={output}
        onClose={jest.fn()}
        onDecided={onDecided}
      />
    );

    fireEvent.change(screen.getByTestId("return-note-input"), {
      target: { value: "add the tax section" },
    });
    fireEvent.click(screen.getByTestId("confirm-return-output"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/build/loops/loop-1/outputs/out-1/decision");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      decision: "return",
      note: "add the tax section",
    });
    await waitFor(() => expect(onDecided).toHaveBeenCalled());
  });
});

describe("GrantModal", () => {
  test("blocks submit until a ship action is chosen in free-entry mode", async () => {
    const fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof fetch;

    renderWithIntl(
      <GrantModal
        loopId="loop-1"
        shipActions={[]}
        open
        onClose={jest.fn()}
        onGranted={jest.fn()}
      />
    );

    fireEvent.click(screen.getByTestId("grant-submit"));
    // Invalid form: no request leaves the page.
    expect(fetchMock).not.toHaveBeenCalled();
    expect(
      screen.getByText("Pick a ship action.", { exact: false })
    ).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("grant-action-input"), {
      target: { value: "im_push" },
    });
    fireEvent.click(screen.getByTestId("grant-submit"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/build/loops/loop-1/grants");
    expect(JSON.parse(init.body as string)).toEqual({
      ship_action: "im_push",
      label: null,
    });
  });
});
