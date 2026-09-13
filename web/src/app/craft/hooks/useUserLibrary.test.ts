import { libraryEntryToApiPath } from "@/app/craft/hooks/useUserLibrary";

describe("libraryEntryToApiPath", () => {
  it("maps the library root to /", () => {
    expect(libraryEntryToApiPath("user_library")).toBe("/");
    expect(libraryEntryToApiPath("/user_library/")).toBe("/");
  });

  it("strips the user_library prefix from nested paths", () => {
    expect(libraryEntryToApiPath("user_library/reports")).toBe("/reports");
    expect(libraryEntryToApiPath("user_library/reports/2026")).toBe(
      "/reports/2026"
    );
  });
});
