import ScenarioEditorPage from "@/views/ScenarioEditorPage";

export interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EditScenarioPage({ params }: PageProps) {
  const { id } = await params;
  return <ScenarioEditorPage scenarioId={id} />;
}
