import Link from "next/link";

const LINKS = [
  { href: "/browse", label: "Browse" },
  { href: "/trending", label: "Trending" },
  { href: "/communities", label: "Communities" },
  { href: "/cities", label: "Cities" },
  { href: "/organizers", label: "Organizers" },
];

export function Footer() {
  return (
    <footer className="mt-16 border-t border-line">
      <div className="container flex flex-col items-center justify-between gap-4 py-8 text-sm text-muted sm:flex-row">
        <p>
          <span className="font-semibold text-ink">EventScout</span> — tech &amp; professional
          events across India.
        </p>
        <nav className="flex flex-wrap items-center justify-center gap-4">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="transition-colors hover:text-ink">
              {l.label}
            </Link>
          ))}
        </nav>
        <p className="text-faint">Aggregated from public sources.</p>
      </div>
    </footer>
  );
}
