import CraftProjectDetailPage from "@/views/CraftProjectDetailPage";

export interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function CraftProjectPage({ params }: PageProps) {
  const { id } = await params;
  return <CraftProjectDetailPage projectId={id} />;
}
