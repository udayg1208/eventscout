/**
 * TypeScript mirror of the backend Platform DTOs
 * (backend/app/platform/dto.py). Field names are snake_case to match the JSON
 * the Platform HTTP surface returns verbatim. Hand-maintained single source of
 * truth on the client — keep in sync with the DTO layer.
 */

export type EventCategory =
  | "workshop"
  | "meetup"
  | "conference"
  | "hackathon"
  | "startup"
  | "ai"
  | "webinar";

export type Lifecycle =
  | "upcoming"
  | "registration_closing"
  | "live_today"
  | "completed"
  | "archived";

export interface EventDTO {
  key: string;
  title: string;
  url: string;
  category: EventCategory;
  start_date: string; // ISO date
  end_date: string | null;
  city: string | null;
  is_online: boolean;
  is_free: boolean | null;
  price: string | null;
  provider: string;
  description: string | null;
}

export interface AIMetadataDTO {
  topics: string[];
  technologies: string[];
  skills: string[];
  audiences: string[];
  difficulty: string; // "Beginner" | "Intermediate" | "Advanced"
  careers: string[];
  summary: string;
}

export interface EntityProfileDTO {
  entity_type: "organization" | "community" | "event_series" | "city";
  name: string;
  total_events: number;
  active_events: number;
  cities: string[];
  extra: Record<string, unknown>; // average_quality, chapters, communities, categories
}

export interface EventDetailDTO {
  event: EventDTO;
  ai: AIMetadataDTO | null;
  lifecycle: Lifecycle;
  trending_score: number;
  similar: EventDTO[];
  organizer: EntityProfileDTO | null;
  community: EntityProfileDTO | null;
  city: EntityProfileDTO | null;
}

export interface RecommendationDTO {
  event: EventDTO;
  score: number;
  reasons: string[];
}

export interface HomepageDTO {
  sections: Record<string, EventDTO[]>;
}

export type Pair = [string, number];

export interface AnalyticsDTO {
  total_events: number;
  cities: number;
  communities: number;
  organizers: number;
  providers: number;
  topics: number;
  technologies: number;
  top_topics: Pair[];
  top_technologies: Pair[];
  top_communities: Pair[];
}

export interface DirectoryDTO {
  organizers: Pair[];
  communities: Pair[];
  series: Pair[];
  cities: Pair[];
}

export interface SearchQuery {
  keywords: string[];
  city: string | null;
  categories: EventCategory[];
  date_from: string | null;
  date_to: string | null;
  free_only: boolean;
}

export interface PlatformSearchResponse {
  query: SearchQuery;
  count: number;
  events: EventDTO[];
}
