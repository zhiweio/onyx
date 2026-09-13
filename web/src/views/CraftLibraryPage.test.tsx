/**
 * @jest-environment jsdom
 */

import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import CraftLibraryPage from "@/views/CraftLibraryPage";
import {
  createLibraryDirectory,
  fetchLibraryTree,
} from "@/app/craft/services/apiServices";
import { SWR_KEYS } from "@/lib/swr-keys";
import type { LibraryEntry } from "@/app/craft/types/user-library";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
  usePathname: () => "/craft/v1/library",
}));

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
  return render(<CraftLibraryPage />, {
    swrConfig: {
      fallback: { [SWR_KEYS.buildUserLibraryTree]: tree },
      revalidateOnMount: false,
      revalidateIfStale: false,
    },
  });
}

describe("CraftLibraryPage", () => {
  beforeEach(() => {
    mockedFetchLibraryTree.mockReset();
    mockedCreateLibraryDirectory.mockReset();
  });

  it("renders a settings page with one empty dropzone", () => {
    renderLibrary();

    expect(screen.getByTestId("CraftLibraryPage/container")).toBeInTheDocument();
    expect(screen.getByLabelText("admin-page-title")).toHaveTextContent(
      "Library"
    );
    expect(
      screen.getByRole("button", { name: "Drag files here or click to upload" })
    ).toBeInTheDocument();
    expect(screen.queryByTestId("file-upload")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the file list and file count without an extra upload well", () => {
    renderLibrary([
      reportsFolder,
      {
        id: "2",
        name: "notes.pdf",
        path: "user_library/notes.pdf",
        is_directory: false,
        file_size: 1024,
        mime_type: "application/pdf",
        sync_enabled: true,
        created_at: "2026-05-28T00:00:00Z",
      },
    ]);

    expect(screen.getByTestId("file-system")).toBeInTheDocument();
    expect(screen.getByText("1 file")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Drag files here or click to upload",
      })
    ).not.toBeInTheDocument();
  });

  it("creates a folder from the page header", async () => {
    mockedCreateLibraryDirectory.mockResolvedValue({
      ...reportsFolder,
      id: "9",
      name: "notes",
      path: "user_library/notes",
    });
    renderLibrary();
    const user = setupUser();

    await user.click(screen.getByRole("button", { name: "New folder" }));
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
  });
});
