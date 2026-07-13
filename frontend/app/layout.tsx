import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Event Discovery — Tech & Professional Events in India",
  description:
    "Discover workshops, meetups, conferences, hackathons and webinars across India using natural language.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

// Set the theme before paint to avoid a flash of the wrong theme.
const themeScript = `
(function () {
  try {
    var t = localStorage.getItem('theme');
    var dark = t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (dark) document.documentElement.classList.add('dark');
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
