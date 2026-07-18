import { EntityDetailPage } from "@/views/EntityDetailPage";

export default async function Page({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return <EntityDetailPage kind="community" name={decodeURIComponent(name)} />;
}
