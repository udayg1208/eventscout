/** Inline SVG icon set (no icon dependency). Each takes an optional className. */
import type { ReactNode } from "react";

interface IconProps {
  className?: string;
}

function make(path: ReactNode, filled = false) {
  function Icon({ className }: IconProps) {
    return (
      <svg
        viewBox="0 0 24 24"
        fill={filled ? "currentColor" : "none"}
        stroke={filled ? "none" : "currentColor"}
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden="true"
      >
        {path}
      </svg>
    );
  }
  return Icon;
}

export const SearchIcon = make(
  <>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </>,
);
export const CalendarIcon = make(
  <>
    <rect x="3" y="4.5" width="18" height="17" rx="2.5" />
    <path d="M3 9.5h18M8 3v3M16 3v3" />
  </>,
);
export const PinIcon = make(
  <>
    <path d="M12 21s-6.5-5.2-6.5-10.2A6.5 6.5 0 0 1 12 4.3a6.5 6.5 0 0 1 6.5 6.5C18.5 15.8 12 21 12 21Z" />
    <circle cx="12" cy="10.8" r="2.3" />
  </>,
);
export const GlobeIcon = make(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c2.5 2.6 2.5 15.4 0 18M12 3c-2.5 2.6-2.5 15.4 0 18" />
  </>,
);
export const ExternalIcon = make(
  <>
    <path d="M14 4h6v6M20 4l-9 9" />
    <path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
  </>,
);
export const SunIcon = make(
  <>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </>,
);
export const MoonIcon = make(<path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8Z" />);
export const BookmarkIcon = make(<path d="M6 4h12v17l-6-4-6 4V4Z" />);
export const BookmarkSolidIcon = make(<path d="M6 3h12a1 1 0 0 1 1 1v17.3a.7.7 0 0 1-1.1.6L12 18l-5.9 3.9A.7.7 0 0 1 5 21.3V4a1 1 0 0 1 1-1Z" />, true);
export const ShareIcon = make(
  <>
    <circle cx="18" cy="5" r="2.5" />
    <circle cx="6" cy="12" r="2.5" />
    <circle cx="18" cy="19" r="2.5" />
    <path d="m8.2 10.8 7.6-4.6M8.2 13.2l7.6 4.6" />
  </>,
);
export const CopyIcon = make(
  <>
    <rect x="9" y="9" width="12" height="12" rx="2" />
    <path d="M5 15V5a2 2 0 0 1 2-2h10" />
  </>,
);
export const ArrowRightIcon = make(<path d="M5 12h14M13 6l6 6-6 6" />);
export const ChevronLeftIcon = make(<path d="m15 6-6 6 6 6" />);
export const ChevronRightIcon = make(<path d="m9 6 6 6-6 6" />);
export const ChevronDownIcon = make(<path d="m6 9 6 6 6-6" />);
export const SparklesIcon = make(
  <>
    <path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3Z" />
    <path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2Z" />
  </>,
);
export const FireIcon = make(
  <path d="M12 3s4.5 3.5 4.5 8a4.5 4.5 0 0 1-9 0c0-1.2.4-2.2.9-3 .1 1 .8 1.8 1.6 1.8 1 0 1.4-1 1-2.4C10.6 5.6 12 3 12 3Z" />,
);
export const TrendingIcon = make(<path d="M3 17l6-6 4 4 7-8M17 7h4v4" />);
export const UsersIcon = make(
  <>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.5 20a5.5 5.5 0 0 1 11 0M16 6.2a3 3 0 0 1 0 5.6M20.5 20a5 5 0 0 0-3.5-4.8" />
  </>,
);
export const BuildingIcon = make(
  <>
    <rect x="5" y="3" width="14" height="18" rx="1.5" />
    <path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2M10 21v-3h4v3" />
  </>,
);
export const TicketIcon = make(
  <>
    <path d="M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2 2 2 0 0 0 0 8 2 2 0 0 1-2 2H6a2 2 0 0 1-2-2 2 2 0 0 0 0-8Z" />
    <path d="M14 6v12" strokeDasharray="2 2" />
  </>,
);
export const FilterIcon = make(<path d="M3 5h18l-7 8v6l-4-2v-4L3 5Z" />);
export const CloseIcon = make(<path d="M6 6l12 12M18 6 6 18" />);
export const CheckIcon = make(<path d="m5 12 5 5 9-11" />);
export const GridIcon = make(
  <>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
  </>,
);
export const ListIcon = make(<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" />);
export const ClockIcon = make(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5V12l3 2" />
  </>,
);
export const TagIcon = make(
  <>
    <path d="M3 12.5V5a2 2 0 0 1 2-2h7.5L21 11.5 12.5 20 3 12.5Z" />
    <circle cx="8" cy="8" r="1.3" />
  </>,
);
export const MenuIcon = make(<path d="M4 6h16M4 12h16M4 18h16" />);
export const LayersIcon = make(<path d="M12 3 3 8l9 5 9-5-9-5ZM3 13l9 5 9-5M3 18l9 4 9-4" />);
export const MapIcon = make(
  <>
    <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z" />
    <path d="M9 4v14M15 6v14" />
  </>,
);
export const BoltIcon = make(<path d="M13 3 4 14h6l-1 7 9-11h-6l1-7Z" />);
export const StarIcon = make(<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3Z" />, true);
export const CompassIcon = make(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" />
  </>,
);
