/**
 * @jest-environment jsdom
 */
import React from "react";
import { act, render, screen, waitFor } from "@tests/setup/test-utils";
import {
  UploadFilesProvider,
  useUploadFilesContext,
} from "@/app/craft/contexts/UploadFilesContext";
import * as api from "@/app/craft/services/apiServices";

jest.mock("@/app/craft/services/apiServices");

const SESSION_A = "11111111-1111-1111-1111-111111111111";
const SESSION_B = "22222222-2222-2222-2222-222222222222";

function Probe() {
  const {
    currentMessageFiles,
    setActiveSession,
    uploadFiles,
    removeFile,
    clearFiles,
  } = useUploadFilesContext();

  return (
    <div>
      <span data-testid="names">
        {currentMessageFiles.map((file) => file.name).join(",")}
      </span>
      <span data-testid="count">{currentMessageFiles.length}</span>
      <button onClick={() => setActiveSession(SESSION_A)}>bind-a</button>
      <button onClick={() => setActiveSession(SESSION_B)}>bind-b</button>
      <button onClick={() => clearFiles()}>clear</button>
      <button
        onClick={() => {
          void uploadFiles([
            new File(["pdf"], "report.pdf", { type: "application/pdf" }),
          ]);
        }}
      >
        attach
      </button>
      <button
        onClick={() => {
          const file = currentMessageFiles[0];
          if (file) removeFile(file.id);
        }}
      >
        remove
      </button>
    </div>
  );
}

function renderProbe() {
  return render(
    <UploadFilesProvider>
      <Probe />
    </UploadFilesProvider>
  );
}

describe("UploadFilesContext draft chips", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(api.uploadFile).mockResolvedValue({
      filename: "report.pdf",
      path: "attachments/report.pdf",
      size_bytes: 3,
    });
    jest.mocked(api.deleteFile).mockResolvedValue(undefined);
    jest.mocked(api.fetchDirectoryListing).mockResolvedValue({
      path: "attachments",
      entries: [
        {
          name: "report.pdf",
          path: "attachments/report.pdf",
          is_directory: false,
          size: 3,
          mime_type: "application/pdf",
        },
      ],
    } as never);
  });

  it("does not hydrate input chips from sandbox attachments", async () => {
    renderProbe();

    await act(async () => {
      screen.getByRole("button", { name: "bind-a" }).click();
    });

    expect(screen.getByTestId("count")).toHaveTextContent("0");
    expect(api.fetchDirectoryListing).not.toHaveBeenCalled();
  });

  it("keeps the input bar empty after send-style clear", async () => {
    renderProbe();

    await act(async () => {
      screen.getByRole("button", { name: "bind-a" }).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: "attach" }).click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("names")).toHaveTextContent("report.pdf");
    });

    await act(async () => {
      screen.getByRole("button", { name: "clear" }).click();
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId("count")).toHaveTextContent("0");
    expect(api.fetchDirectoryListing).not.toHaveBeenCalled();
  });

  it("drops completed chips when switching sessions", async () => {
    renderProbe();

    await act(async () => {
      screen.getByRole("button", { name: "bind-a" }).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: "attach" }).click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("names")).toHaveTextContent("report.pdf");
    });

    await act(async () => {
      screen.getByRole("button", { name: "bind-b" }).click();
    });

    expect(screen.getByTestId("count")).toHaveTextContent("0");
  });

  it("does not restore a chip when sandbox delete returns not found", async () => {
    jest
      .mocked(api.deleteFile)
      .mockRejectedValue(new Error("Failed to delete file: 404"));

    renderProbe();

    await act(async () => {
      screen.getByRole("button", { name: "bind-a" }).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: "attach" }).click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("names")).toHaveTextContent("report.pdf");
    });

    await act(async () => {
      screen.getByRole("button", { name: "remove" }).click();
    });
    await waitFor(() => {
      expect(api.deleteFile).toHaveBeenCalledWith(
        SESSION_A,
        "attachments/report.pdf"
      );
    });

    expect(screen.getByTestId("count")).toHaveTextContent("0");
  });
});
