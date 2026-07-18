import { SearchPage } from "@/views/SearchPage";

export const metadata = { title: "Search — EventScout" };

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const sp = await searchParams;
  const q = typeof sp.q === "string" ? sp.q : "";
  return <SearchPage initialQuery={q} />;
}
