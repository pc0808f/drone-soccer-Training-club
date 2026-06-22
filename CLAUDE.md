# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A single-file static marketing landing page (`index.html`) for the **2026 兩岸無人機足球研習營** (Cross-Strait Drone Soccer Training Camp), an event held in Xiamen. Content is in Traditional Chinese (`lang="zh-TW"`).

There is no build system, package manager, framework, test suite, or version control. The deliverable is the raw HTML file — open it directly in a browser to preview, and deploy by copying the file to any static host.

## Architecture

Everything lives in `index.html`: an inline `<style>` block followed by the page markup. There is no JavaScript — the "立即報名" (register) CTA button is a styled `<div>`, not a functional link.

- **Styling** is driven by CSS custom properties defined in `:root` (color palette, `--card-shadow`). Reuse these variables instead of hardcoding colors so the theme stays consistent.
- **Layout** is mobile-first; responsive grids collapse to a single column via `@media (max-width: 480px–500px)` queries.
- **Sections** follow a repeated pattern: a `.section` wrapper containing `.section-label` (eyebrow) + `.section-title`, separated by `<hr class="divider">`. The page flows: hero → organizers → event info → instructors → 6-day schedule → takeaways → career opportunities → costs → CTA → footer.

## Working in this repo

- Edit content and styles in place; keep new markup consistent with the existing class-based component patterns (`.info-card`, `.schedule-item`, `.get-card`, etc.).
- **Unfilled placeholders** are marked with `【待填：...】` (Chinese for "to be filled"). Several remain in the live content — e.g. Day 5 itinerary details and the contact name/LINE/phone in the CTA block. Do not invent values for these; flag them or ask the user.
- Preserve the bilingual-free, Traditional Chinese tone and the FIDA / 世界盃 (World Cup) framing when editing copy.
