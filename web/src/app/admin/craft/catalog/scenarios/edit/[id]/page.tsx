import CatalogScenarioEditorPage from "@/views/admin/CatalogScenarioEditorPage";

export interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EditCatalogScenarioPage({ params }: PageProps) {
  const { id } = await params;
  return <CatalogScenarioEditorPage entryId={id} />;
}
