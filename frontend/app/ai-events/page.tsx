import { FeedPage } from "@/views/FeedPage";
import { FEEDS } from "@/utils/feeds";

export const metadata = { title: "AI Events — EventScout" };

export default function Page() {
  return <FeedPage meta={FEEDS["ai-events"]} />;
}
