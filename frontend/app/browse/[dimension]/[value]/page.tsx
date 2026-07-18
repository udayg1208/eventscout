import { BrowseResults } from "@/views/BrowseResults";
import type { BrowseDimension } from "@/services/platform";

export default async function Page({
  params,
}: {
  params: Promise<{ dimension: string; value: string }>;
}) {
  const { dimension, value } = await params;
  return (
    <BrowseResults
      dimension={dimension as BrowseDimension}
      value={decodeURIComponent(value)}
    />
  );
}
