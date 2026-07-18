"use client";

import { useState } from "react";

import { Button } from "./ui/Button";
import { CheckIcon, ShareIcon } from "./ui/icons";

/** Native share where available, clipboard copy as a fallback. */
export function ShareButton({
  title,
  url,
  showLabel = true,
}: {
  title: string;
  url: string;
  showLabel?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  async function share() {
    const nav = navigator as Navigator & {
      share?: (data: ShareData) => Promise<void>;
    };
    if (nav.share) {
      try {
        await nav.share({ title, url });
        return;
      } catch {
        return; // user cancelled the share sheet
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked */
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={share}>
      {copied ? <CheckIcon className="h-4 w-4" /> : <ShareIcon className="h-4 w-4" />}
      {showLabel && (copied ? "Copied" : "Share")}
    </Button>
  );
}
