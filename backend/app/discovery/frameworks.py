"""FrameworkDetector — identify the JS framework from raw HTML markers (no JS execution).

Deterministic: each framework has stable, static fingerprints (script ids, asset paths, global
hooks) present in the served HTML. Version is reported only when a marker actually exposes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FrameworkInfo:
    name: str | None = None
    version: str | None = None


_NUXT3_VER = re.compile(r'"nuxt":"3[.\d]*"|/_nuxt/[^"\']*', re.IGNORECASE)


def detect_framework(html: str) -> FrameworkInfo:
    low = html.lower()

    # Next.js — Pages Router (__NEXT_DATA__) or App Router (self.__next_f / RSC)
    if 'id="__next_data__"' in low or "self.__next_f" in html or "__next_f.push" in html:
        version = "app-router" if "self.__next_f" in html else "pages-router"
        return FrameworkInfo("Next.js", version)
    if "/_next/static/" in low:
        return FrameworkInfo("Next.js", None)

    # Nuxt — v3 (__NUXT_DATA__ json script) vs v2 (window.__NUXT__ function)
    if 'id="__nuxt_data__"' in low:
        return FrameworkInfo("Nuxt", "3")
    if "window.__nuxt__" in low or "/_nuxt/" in low:
        return FrameworkInfo("Nuxt", "2" if "window.__nuxt__" in low else None)

    # Remix
    if "__remixcontext" in low or "__remixmanifest" in low or "__remixroutemodules" in low:
        return FrameworkInfo("Remix", None)

    # Gatsby
    if 'id="___gatsby"' in low or "/page-data/" in low or "window.___gatsby" in low:
        return FrameworkInfo("Gatsby", None)

    # SvelteKit
    if "__sveltekit" in low or "/_app/immutable/" in low:
        return FrameworkInfo("SvelteKit", None)

    # Astro
    if "astro-island" in low or "/_astro/" in low or "data-astro-" in low:
        return FrameworkInfo("Astro", None)

    # Vite (bundler; usually React/Vue SPA)
    if "/@vite/client" in low or re.search(r'type="module"[^>]*src="/assets/index-', low):
        return FrameworkInfo("Vite", None)

    # Apollo state present (framework usually React)
    if "window.__apollo_state__" in low:
        return FrameworkInfo("React (Apollo)", None)

    # Generic client-rendered React SPA — an empty #root shell with a JS bundle.
    if re.search(r'<div id="root"[^>]*>\s*</div>', html, re.IGNORECASE) and (
        "react" in low or "/static/js/" in low
    ):
        return FrameworkInfo("React SPA", None)

    return FrameworkInfo(None, None)
