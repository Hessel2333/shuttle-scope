import { AnalysisDetailClient } from "@/components/AnalysisDetailClient";

export default async function AnalysisDetailPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  return <AnalysisDetailClient jobId={jobId} />;
}
