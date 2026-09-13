/**
 * @jest-environment jsdom
 */

import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import UserLibraryModal from "@/app/craft/components/UserLibraryModal";
import {
  createLibraryDirectory,
  fetchLibraryTree,
} from "@/app/craft/services/apiServices";
import { SWR_KEYS } from "@/lib/swr-keys";
import type { LibraryEntry } from "@/app/craft/types/user-library";

jest.mock("@/app/craft/services/apiServices", () => ({
  ...jest.requireActual("@/app/craft/services/apiServices"),
  fetchLibraryTree: jest.fn(),
  createLibraryDirectory: jest.fn(),
  uploadLibraryFiles: jest.fn(),
  uploadLibraryZip: jest.fn(),
  deleteLibraryFile: jest.fn(),
}));

jest.mock("@/sections/extend/file-system", () => ({
  FileSystem: () => <div data-testid="file-system" />,
}));

const mockedFetchLibraryTree = jest.mocked(fetchLibraryTree);
const mockedCreateLibraryDirectory = jest.mocked(createLibraryDirectory);

const reportsFolder: LibraryEntry = {
  id: "1",
  name: "reports",
  path: "user_library/reports",
  is_directory: true,
  file_size: null,
  mime_type: null,
  sync_enabled: true,
  created_at: "2026-05-28T00:00:00Z",
};

function renderLibrary(tree: LibraryEntry[] = []) {
  mockedFetchLibraryTree.mockResolvedValue(tree);
  return render(<UserLibraryModal open onClose={jest.fn()} />, {
    swrConfig: {
      fallback: { [SWR_KEYS.buildUserLibraryTree]: tree },
      revalidateOnMount: false,
      revalidateIfStale: false,
    },
  });
}

async function openCreateFolder() {
  const user = setupUser();
  await user.click(screen.getByRole("button", { name: "New folder" }));
  return user;
}

describe("UserLibraryModal layout", () => {
  beforeEach(() => {
    mockedFetchLibraryTree.mockReset();
    mockedCreateLibraryDirectory.mockReset();
  });

  it("shows one empty dropzone and no second upload well", () => {
    renderLibrary();

    expect(
      screen.getByRole("button", { name: "Drag files here or click to upload" })
    ).toBeInTheDocument();
    expect(screen.queryByTestId("file-upload")).not.toBeInTheDocument();
    expect(screen.queryByTestId("file-system")).not.toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Personal files for every conversation. Project files stay on the project page."
      ).length
    ).toBeGreaterThan(0);
  });

  it("shows the file list without an extra upload well", () => {
    renderLibrary([reportsFolder]);

    expect(screen.getByTestId("file-system")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Drag files here or click to upload",
      })
    ).not.toBeInTheDocument();
  });
});

describe("UserLibraryModal create folder", () => {
  beforeEach(() => {
    mockedFetchLibraryTree.mockReset();
    mockedCreateLibraryDirectory.mockReset();
  });

  it("opens an inline panel instead of a second modal", async () => {
    renderLibrary();

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(
      screen.queryByRole("form", { name: "New folder" })
    ).not.toBeInTheDocument();

    await openCreateFolder();

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(
      screen.getByRole("form", { name: "New folder" })
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("Enter folder name")
    ).toBeInTheDocument();
  });

  it("keeps Create disabled for an empty or whitespace name", async () => {
    renderLibrary();
    const user = await openCreateFolder();

    const createButton = screen.getByRole("button", { name: "Create" });
    expect(createButton).toBeDisabled();

    await user.type(screen.getByPlaceholderText("Enter folder name"), "   ");
    expect(createButton).toBeDisabled();
    expect(mockedCreateLibraryDirectory).not.toHaveBeenCalled();
  });

  it("cancels and hides the inline panel", async () => {
    renderLibrary();
    const user = await openCreateFolder();

    await user.type(screen.getByPlaceholderText("Enter folder name"), "drafts");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(
      screen.queryByRole("form", { name: "New folder" })
    ).not.toBeInTheDocument();
    expect(mockedCreateLibraryDirectory).not.toHaveBeenCalled();
  });

  it("creates a folder with the existing API and closes the panel", async () => {
    mockedCreateLibraryDirectory.mockResolvedValue({
      ...reportsFolder,
      id: "9",
      name: "notes",
      path: "user_library/notes",
    });
    renderLibrary();
    const user = await openCreateFolder();

    await user.type(
      screen.getByPlaceholderText("Enter folder name"),
      "  notes  "
    );
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(mockedCreateLibraryDirectory).toHaveBeenCalledWith({
        name: "notes",
        parent_path: "/",
      });
    });
    await waitFor(() => {
      expect(
        screen.queryByRole("form", { name: "New folder" })
      ).not.toBeInTheDocument();
    });
  });
});
