import { redirect } from "next/navigation";

// Agent runtime model overlays merged into the Language Models page.
export default function AgentModelsRedirectPage(): never {
  redirect("/admin/language-models?tab=agent-models");
}
