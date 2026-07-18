import { FeedPage } from "@/views/FeedPage";
import type { EventCategory } from "@/types/platform";
import { CATEGORY_LABEL } from "@/utils/categories";

export default async function Page({
  params,
}: {
  params: Promise<{ category: string }>;
}) {
  const { category } = await params;
  const c = category as EventCategory;
  const label = CATEGORY_LABEL[c] ?? category;
  return (
    <FeedPage
      meta={{
        slug: `categories/${category}`,
        title: `${label} Events`,
        description: `Browse ${label} events across India.`,
        source: { kind: "category", category: c },
      }}
    />
  );
}
