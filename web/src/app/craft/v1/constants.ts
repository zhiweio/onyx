export const CRAFT_PATH = "/craft/v1";
export const CRAFT_TASKS_PATH = `${CRAFT_PATH}/tasks`;
export const CRAFT_SKILLS_PATH = `${CRAFT_PATH}/skills`;
export const CRAFT_SCENARIOS_PATH = `${CRAFT_PATH}/scenarios`;
export const CRAFT_REPORT_TEMPLATES_PATH = `${CRAFT_PATH}/report-templates`;
export const CRAFT_PROJECTS_PATH = `${CRAFT_PATH}/projects`;
export const CRAFT_APPS_PATH = `${CRAFT_PATH}/apps`;
export const CRAFT_MCP_ACTIONS_PATH = `${CRAFT_PATH}/mcp-actions`;
export const CRAFT_OAUTH_COOKIE_NAME = "build_mode_oauth";

// Backend BFF root for Craft/build endpoints (routes through the frontend
// per CLAUDE.md). Shared by the craft service modules.
export const BUILD_API_BASE = "/api/build";
