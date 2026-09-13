import type {
  CraftProjectFile,
  CraftProjectSession,
} from "@/lib/craft-projects/types";
import {
  compareProjectFiles,
  compareProjectSessions,
  fileExtension,
  fileKind,
  fileTitleSource,
  generatedDumpSuffix,
  isGeneratedDumpName,
  isImplicitUntitledProject,
  isProjectMainSession,
  normalizeSessionStatus,
  parseSessionLane,
  pathLooksLikeMcp,
  formatProjectFileText,
  groupProjectFilesByFolder,
  projectFilePreviewKind,
  projectHeadline,
  projectNeedsRefresh,
  projectSandboxStatus,
  projectSessionDisplayStatus,
  projectSessionNeedsRefresh,
  sessionListLabel,
  sidebarListTitle,
  stripInternalProjectSuffix,
  usefulFolder,
} from "@/lib/craft-projects/display";

function file(
  overrides: Partial<CraftProjectFile> & Pick<CraftProjectFile, "name" | "path">
): CraftProjectFile {
  return {
    id: overrides.id ?? overrides.name,
    project_id: "proj",
    mime_type: null,
    size_bytes: 1,
    content_hash: null,
    source: "session_output",
    produced_by_session_id: null,
    version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function session(overrides: Partial<CraftProjectSession>): CraftProjectSession {
  return {
    id: overrides.id ?? "session",
    name: overrides.name ?? "Chat",
    status: overrides.status ?? "IDLE",
    origin: overrides.origin,
    job_status: overrides.job_status,
    has_active_turn: overrides.has_active_turn,
    created_at: "2026-08-01T00:00:00Z",
    last_activity_at: overrides.last_activity_at ?? "2026-08-01T00:00:00Z",
  };
}

describe("craft project display helpers", () => {
  it("classifies extensions and generated dump names", () => {
    expect(fileExtension("claim-map.md")).toBe("md");
    expect(fileKind(file({ name: "rates.xlsx", path: "/rates.xlsx" }))).toBe(
      "table"
    );
    expect(isGeneratedDumpName("1788711879701.json")).toBe(true);
    expect(isGeneratedDumpName("claim-map.md")).toBe(false);
    expect(generatedDumpSuffix("1788711879701.json")).toBe("9701");
  });

  it("prefers a useful folder over generic MCP path segments", () => {
    expect(usefulFolder("outputs/mcp/bash/1788711879701.json")).toBe("bash");
    expect(usefulFolder("outputs/mcp/1788711879701.json")).toBeNull();
    expect(pathLooksLikeMcp("outputs/mcp/1788711879701.json")).toBe(true);
    expect(
      fileTitleSource(file({ name: "patent.csv", path: "patent.csv" }))
    ).toEqual({ source: "original", folder: null });
    expect(
      fileTitleSource(
        file({
          name: "1788711879701.json",
          path: "outputs/mcp/bash/1788711879701.json",
        })
      )
    ).toEqual({ source: "folder", folder: "bash" });
    expect(
      fileTitleSource(
        file({
          name: "1788711879701.json",
          path: "outputs/mcp/1788711879701.json",
        })
      )
    ).toEqual({ source: "mcp", folder: null });
  });

  it("splits a long specialist title from the trailing lane role", () => {
    const name =
      "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由 / literature";
    expect(parseSessionLane(name)).toEqual({
      role: "literature",
      goal: "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由",
    });
    expect(parseSessionLane("First pass")).toEqual({
      role: null,
      goal: "First pass",
    });
    expect(normalizeSessionStatus("ACTIVE")).toBe("active");
    expect(
      sessionListLabel(
        "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由 / literature"
      )
    ).toEqual({
      role: "literature",
      text: "literature",
      full: "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由 / literature",
    });
    expect(sessionListLabel("Research GLP-1 literature domain").role).toBe(
      "literature"
    );
    expect(sessionListLabel("Research GLP-1 clinical landscape").role).toBe(
      "clinical"
    );
    expect(sessionListLabel("Research GLP-1 CMC quality domain").role).toBe(
      "cmc"
    );
    expect(sessionListLabel("GLP-1 立项报告")).toEqual({
      role: null,
      text: "GLP-1 立项报告",
      full: "GLP-1 立项报告",
    });
  });

  it("strips blackboard for one-line sidebar titles", () => {
    const longName =
      "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。 blackboard";
    expect(stripInternalProjectSuffix(longName)).toBe(
      "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。"
    );
    expect(sidebarListTitle(longName)).toEqual({
      text: "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。",
      tooltip:
        "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。",
    });
    expect(sidebarListTitle("GLP-1 立项报告")).toEqual({
      text: "GLP-1 立项报告",
      tooltip: "GLP-1 立项报告",
    });
  });

  it("strips blackboard and shortens a long project prompt", () => {
    const longName =
      "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。 blackboard";
    expect(projectHeadline(longName)).toEqual({
      title: "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告",
      full: "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。",
    });
    expect(projectHeadline("年报税务复核")).toEqual({
      title: "年报税务复核",
      full: "年报税务复核",
    });
  });

  it("classifies preview kinds and groups files by folder", () => {
    expect(
      projectFilePreviewKind(
        file({ name: "report.md", path: "outputs/report.md" })
      )
    ).toBe("markdown");
    expect(
      projectFilePreviewKind(
        file({
          name: "PLAN.json",
          path: "outputs/plan/PLAN.json",
          mime_type: "application/json",
        })
      )
    ).toBe("json");
    expect(
      projectFilePreviewKind(file({ name: "notes.txt", path: "notes.txt" }))
    ).toBe("text");
    expect(
      projectFilePreviewKind(
        file({
          name: "report.html",
          path: "/君禾股份_财报解读_2026H1.html",
          mime_type: "text/html",
        })
      )
    ).toBe("html");
    expect(
      projectFilePreviewKind(
        file({ name: "chart.png", path: "chart.png", mime_type: "image/png" })
      )
    ).toBe("image");
    expect(
      projectFilePreviewKind(
        file({
          name: "rates.xlsx",
          path: "/rates.xlsx",
          mime_type: "application/vnd.ms-excel",
        })
      )
    ).toBe("xlsx");
    expect(
      projectFilePreviewKind(file({ name: "report.docx", path: "report.docx" }))
    ).toBe("docx");
    expect(
      projectFilePreviewKind(file({ name: "brief.pdf", path: "brief.pdf" }))
    ).toBe("pdf");
    expect(formatProjectFileText('{"a":1}', "json")).toBe('{\n  "a": 1\n}');
    expect(formatProjectFileText("not-json", "json")).toBe("not-json");

    const groups = groupProjectFilesByFolder([
      file({
        name: "FINDINGS.md",
        path: "project/research/literature/FINDINGS.md",
      }),
      file({ name: "rates.xlsx", path: "/rates.xlsx" }),
      file({ name: "PLAN.json", path: "outputs/plan/PLAN.json" }),
    ]);
    expect(groups.map((group) => group.folder)).toEqual([
      "",
      "outputs/plan",
      "project/research/literature",
    ]);
    expect(groups[0]?.files.map((item) => item.name)).toEqual(["rates.xlsx"]);
  });

  it("sorts named documents before generated dumps, and active chats first", () => {
    const files = [
      file({ name: "1788711879701.json", path: "outputs/mcp/a.json" }),
      file({ name: "patent.csv", path: "patent.csv" }),
      file({ name: "claim-map.md", path: "claim-map.md" }),
    ].sort(compareProjectFiles);
    expect(files.map((item) => item.name)).toEqual([
      "claim-map.md",
      "patent.csv",
      "1788711879701.json",
    ]);

    const sessions = [
      session({
        id: "idle",
        status: "IDLE",
        last_activity_at: "2026-08-02T00:00:00Z",
      }),
      session({
        id: "active",
        status: "ACTIVE",
        last_activity_at: "2026-08-01T00:00:00Z",
      }),
    ].sort(compareProjectSessions);
    expect(sessions.map((item) => item.id)).toEqual(["active", "idle"]);
  });

  it("keeps only the main interactive chat and hides planned lanes", () => {
    expect(
      isProjectMainSession(
        session({ id: "main", origin: "INTERACTIVE", status: "ACTIVE" })
      )
    ).toBe(true);
    expect(
      isProjectMainSession(
        session({
          id: "lane",
          origin: "JOB",
          name: "Report / visualize-and-compose",
          status: "ACTIVE",
        })
      )
    ).toBe(false);
  });

  it("treats a finished job as idle even when the sandbox is still active", () => {
    expect(
      projectSessionDisplayStatus(
        session({
          origin: "INTERACTIVE",
          status: "ACTIVE",
          job_status: "succeeded",
          has_active_turn: false,
        })
      )
    ).toBe("idle");
    expect(
      projectSessionDisplayStatus(
        session({
          origin: "INTERACTIVE",
          status: "ACTIVE",
          job_status: "running",
          has_active_turn: false,
        })
      )
    ).toBe("active");
    expect(
      projectSessionDisplayStatus(
        session({
          origin: "INTERACTIVE",
          status: "ACTIVE",
          job_status: "succeeded",
          has_active_turn: true,
        })
      )
    ).toBe("active");
    expect(
      projectSessionNeedsRefresh(
        session({
          origin: "INTERACTIVE",
          status: "IDLE",
          job_status: "succeeded",
        })
      )
    ).toBe(false);
    expect(projectSandboxStatus(undefined)).toBe("missing");
    expect(
      projectSandboxStatus({
        status: "running",
        last_heartbeat: "2026-08-01T00:00:00Z",
        created_at: "2026-08-01T00:00:00Z",
      })
    ).toBe("running");
    expect(
      projectNeedsRefresh({
        id: "proj",
        name: "Tax",
        description: "",
        instructions: null,
        file_count: 0,
        session_count: 0,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
        sandbox: {
          status: "provisioning",
          last_heartbeat: null,
          created_at: "2026-08-01T00:00:00Z",
        },
      })
    ).toBe(true);
  });
});

describe("isImplicitUntitledProject", () => {
  it("hides empty auto-created Untitled projects", () => {
    expect(
      isImplicitUntitledProject({
        name: "Untitled project",
        description: "",
        instructions: null,
      })
    ).toBe(true);
  });

  it("keeps named or instructed projects", () => {
    expect(
      isImplicitUntitledProject({
        name: "Tax pack",
        description: "",
        instructions: null,
      })
    ).toBe(false);
    expect(
      isImplicitUntitledProject({
        name: "Untitled project",
        description: "",
        instructions: "Be brief.",
      })
    ).toBe(false);
  });
});
