import { FeedPage } from "@/views/FeedPage";
import { FEEDS } from "@/utils/feeds";

export const metadata = { title: "Closing Soon — EventScout" };

export default function Page() {
  return <FeedPage meta={FEEDS["closing-soon"]} />;
}
