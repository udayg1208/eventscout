import { FeedPage } from "@/views/FeedPage";
import { FEEDS } from "@/utils/feeds";

export const metadata = { title: "Developer Festivals — EventScout" };

export default function Page() {
  return <FeedPage meta={FEEDS["developer-festivals"]} />;
}
