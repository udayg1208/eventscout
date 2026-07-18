import type { Metadata, Viewport } from "next";

import { AppShell } from "@/layouts/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: "EventScout — Tech & Professional Events across India",
  description:
    "Discover, search, and get recommendations for workshops, meetups, conferences, hackathons, and AI events across India.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

// Set the theme before paint to avoid a flash of the wrong theme.
// Default is DARK for now: with no saved preference we open in dark mode (ignoring the OS
// setting). An explicit choice via the toggle is still respected and persisted.
const themeScript = `
(function () {
  try {
    var t = localStorage.getItem('theme');
    var dark = t ? t === 'dark' : true;
    if (dark) document.documentElement.classList.add('dark');
  } catch (e) {
    document.documentElement.classList.add('dark');
  }
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
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
