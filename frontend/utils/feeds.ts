/**
 * Feed registry — one parameterized template (`FeedPage`) powers every "list of
 * events" route. Each entry declares where its events come from (a discovery
 * endpoint, a category browse, or a homepage section) so the page stays generic.
 */

import type { BrowseDimension, DiscoverFeed } from "@/services/platform";
import type { EventCategory } from "@/types/platform";

export type FeedSource =
  | { kind: "discover"; feed: DiscoverFeed }
  | { kind: "category"; category: EventCategory }
  | { kind: "section"; section: string };

export interface FeedMeta {
  slug: string;
  title: string;
  description: string;
  source: FeedSource;
}

export const FEEDS: Record<string, FeedMeta> = {
  trending: {
    slug: "trending",
    title: "Trending Events",
    description: "The events gaining the most momentum right now.",
    source: { kind: "discover", feed: "trending" },
  },
  new: {
    slug: "new",
    title: "New Events",
    description: "Freshly added to the catalog.",
    source: { kind: "discover", feed: "newest" },
  },
  "closing-soon": {
    slug: "closing-soon",
    title: "Registration Closing Soon",
    description: "Register before the window closes.",
    source: { kind: "discover", feed: "registration-closing" },
  },
  "ai-events": {
    slug: "ai-events",
    title: "AI Events",
    description: "Artificial intelligence, machine learning, and generative AI.",
    source: { kind: "category", category: "ai" },
  },
  hackathons: {
    slug: "hackathons",
    title: "Hackathons",
    description: "Build something in a weekend.",
    source: { kind: "category", category: "hackathon" },
  },
  conferences: {
    slug: "conferences",
    title: "Conferences",
    description: "Multi-track events with talks and networking.",
    source: { kind: "category", category: "conference" },
  },
  meetups: {
    slug: "meetups",
    title: "Meetups",
    description: "Community gatherings, big and small.",
    source: { kind: "category", category: "meetup" },
  },
  workshops: {
    slug: "workshops",
    title: "Workshops",
    description: "Hands-on, learn-by-doing sessions.",
    source: { kind: "category", category: "workshop" },
  },
  "startup-events": {
    slug: "startup-events",
    title: "Startup Events",
    description: "Pitches, demo days, and founder gatherings.",
    source: { kind: "category", category: "startup" },
  },
  "developer-festivals": {
    slug: "developer-festivals",
    title: "Developer Festivals",
    description: "Large-scale developer festivals like DevFest.",
    source: { kind: "section", section: "developer_festivals" },
  },
  "university-events": {
    slug: "university-events",
    title: "University Tech Events",
    description: "Campus hackathons, fests, and student tech.",
    source: { kind: "section", section: "university_events" },
  },
  "government-tech": {
    slug: "government-tech",
    title: "Government Tech Events",
    description: "Public-sector and e-governance technology events.",
    source: { kind: "section", section: "government_tech" },
  },
  online: {
    slug: "online",
    title: "Online Events",
    description: "Attend from anywhere.",
    source: { kind: "discover", feed: "online" },
  },
  free: {
    slug: "free",
    title: "Free Events",
    description: "No ticket required.",
    source: { kind: "discover", feed: "free" },
  },
};

/** Browse dimensions offered on the Browse hub. */
export interface BrowseMeta {
  dimension: BrowseDimension;
  title: string;
  placeholder: string;
  examples: string[];
}

export const BROWSE_DIMENSIONS: BrowseMeta[] = [
  { dimension: "topic", title: "Topic", placeholder: "e.g. Artificial Intelligence", examples: ["Artificial Intelligence", "Cloud", "DevOps", "Open Source", "Startup"] },
  { dimension: "technology", title: "Technology", placeholder: "e.g. Python", examples: ["Python", "Kubernetes", "React", "Gemini", "AWS"] },
  { dimension: "city", title: "City", placeholder: "e.g. Bangalore", examples: ["Bangalore", "Delhi", "Mumbai", "Pune", "Hyderabad"] },
  { dimension: "difficulty", title: "Difficulty", placeholder: "Beginner / Intermediate / Advanced", examples: ["Beginner", "Intermediate", "Advanced"] },
  { dimension: "audience", title: "Audience", placeholder: "e.g. Students", examples: ["Students", "Developers", "Founders", "Data Scientists"] },
  { dimension: "community", title: "Community", placeholder: "e.g. Google Developer Groups", examples: ["Google Developer Groups", "FOSS United", "Hasgeek", "CNCF"] },
  { dimension: "organizer", title: "Organizer", placeholder: "e.g. Google", examples: ["Google", "Razorpay", "Microsoft"] },
];
