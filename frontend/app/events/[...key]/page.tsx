import { EventDetailPage } from "@/views/EventDetailPage";
import { resolveEventKey } from "@/utils/eventKey";

export default async function Page({
  params,
}: {
  params: Promise<{ key: string[] }>;
}) {
  const { key } = await params;
  // `key` is a single opaque base64url token (new) or a legacy raw-key path (old bookmarks).
  return <EventDetailPage eventKey={resolveEventKey(key)} />;
}
