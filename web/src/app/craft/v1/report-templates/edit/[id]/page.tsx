import ReportTemplateEditorPage from "@/views/ReportTemplateEditorPage";

export interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EditReportTemplatePage({ params }: PageProps) {
  const { id } = await params;
  return <ReportTemplateEditorPage templateId={id} />;
}
