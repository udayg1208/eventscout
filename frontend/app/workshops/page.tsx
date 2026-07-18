import { FeedPage } from "@/views/FeedPage";
import { FEEDS } from "@/utils/feeds";

export const metadata = { title: "Workshops — EventScout" };

export default function Page() {
  return <FeedPage meta={FEEDS.workshops} />;
}
