import { FeedPage } from "@/views/FeedPage";
import { FEEDS } from "@/utils/feeds";

export const metadata = { title: "University Tech Events — EventScout" };

export default function Page() {
  return <FeedPage meta={FEEDS["university-events"]} />;
}
