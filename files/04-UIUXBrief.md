# UI/UX Design Brief — Arc
### Visual & Interaction Design Specification

---

## Aesthetic Direction

Arc is a **personal intelligence tool** — not a consumer app, not a SaaS dashboard. It sits in the same mental category as tools like Obsidian, Linear, and Raycast: opinionated, minimal, built for a single power user who wants zero friction between thought and capture.

**Direction: Dark mode primary. Minimal. Dense where needed. No decorative elements.**

The mobile app should look like a focused, slightly premium voice recorder — the kind of app that ships on a flagship phone. Nothing should suggest surveillance or complexity. One screen. One button. Clean.

The web UI should feel like a local-first developer tool — think of how a well-designed terminal dashboard looks. Not corporate SaaS. Not a startup landing page. Calm, functional, information-dense without feeling cluttered.

Reference aesthetic: **Raycast + Obsidian + Linear**

---

## Color Palette

### Mobile App

| Role | Hex | Usage |
|------|-----|-------|
| Background | `#0A0A0A` | Full screen background |
| Surface | `#141414` | Card backgrounds, bottom sheets |
| Record Button (idle) | `#FFFFFF` | Large circle, idle state |
| Record Button (active) | `#EF4444` | Red when recording — clear visual signal |
| Text Primary | `#F5F5F5` | Timer, labels |
| Text Secondary | `#6B7280` | Status hints, metadata |
| Accent | `#6366F1` | Upload progress, success states |
| Destructive | `#EF4444` | Shared with active record (deliberate) |

### Web UI

| Role | Hex | Usage |
|------|-----|-------|
| Background | `#0D0D0D` | Page background |
| Surface | `#161616` | Cards, sidebar, table rows |
| Surface Elevated | `#1E1E1E` | Modals, active rows, hover states |
| Border | `#2A2A2A` | Dividers, card outlines |
| Text Primary | `#EFEFEF` | Headings, table content |
| Text Secondary | `#737373` | Timestamps, labels, captions |
| Accent | `#6366F1` | Links, active badges, CTA buttons |
| Success | `#22C55E` | "Done" status badge |
| Warning | `#F59E0B` | "Needs naming" status badge |
| Processing | `#3B82F6` | "Processing" animated badge |
| Error | `#EF4444` | "Error" status badge |

---

## Typography

| Use | Font | Weight | Size |
|-----|------|--------|------|
| UI (both surfaces) | Inter | Variable | — |
| Headings (web) | Inter | 600 | 20px / 16px |
| Body text | Inter | 400 | 14px |
| Captions, timestamps | Inter | 400 | 12px |
| Transcript text | `JetBrains Mono` | 400 | 13px |
| Timer display (mobile) | Inter | 300 (thin) | 48px |
| Speaker labels | Inter | 500 | 13px |

> Transcript content uses monospace — it reads like a document, not a chat. This is intentional.

---

## Component Style

| Property | Value |
|----------|-------|
| Border Radius | 8px (cards, buttons) / 4px (badges, inputs) / 50% (record button circle) |
| Shadows | None — borders define surfaces instead (consistent with dark mode) |
| Density | Compact for web UI (information-dense table rows) / Spacious for mobile (large tap targets) |
| Transitions | 150ms ease — fast, not flashy |
| Focus rings | `#6366F1` 2px outline — keyboard accessible |

---

## Mode

**Dark mode only** — both surfaces. No light mode toggle in v1.

Rationale: recording happens in meeting rooms (ambient light varies). A dark screen is less conspicuous. The web UI is used at a desk during focused review — dark mode reduces eye strain during late sessions.

---

## Mobile App — Key UI Patterns

### RecorderScreen

```
┌─────────────────────────────────┐
│                                 │
│                                 │
│          [00:00:00]             │  ← thin Inter timer, center
│                                 │
│                                 │
│          ●  [  ]  ●             │  ← large circle button, 96px diameter
│                                 │     white (idle) / red + pulse (recording)
│                                 │
│     Tap to record               │  ← secondary text, disappears on first tap
│                                 │
│  ─────────────────────────────  │
│  Last session: 2h ago · 47min   │  ← last upload summary, subtle
└─────────────────────────────────┘
```

- No navigation bar
- No hamburger menu
- No settings visible on this screen
- The notification during recording: "Arc · 12:34 · Recording in progress"

### QRScannerScreen

```
┌─────────────────────────────────┐
│  ←  Pair with laptop            │
│                                 │
│  ┌─────────────────────────┐    │
│  │                         │    │
│  │    [camera viewfinder]  │    │
│  │         [  QR  ]        │    │
│  │                         │    │
│  └─────────────────────────┘    │
│                                 │
│  Open Arc server on your        │
│  laptop, then scan the QR.      │
│                                 │
└─────────────────────────────────┘
```

---

## Web UI — Key UI Patterns

### Dashboard Table

Each meeting row contains:
- Date + time (left)
- Duration (right of date)
- Participants list — speaker names, comma separated (middle)
- Status badge (right) — colour-coded per state machine
- Click anywhere on row → Meeting Detail

### Status Badges

```
● Done          ← green dot + text
◌ Processing    ← blue animated dot
⚠ Needs naming  ← amber, clickable → /naming/{id}
✕ Error         ← red, hover shows reason
◷ Pending       ← grey dot
```

### Speaker Naming UI

- Each unknown speaker gets a card
- Card has: speaker number, waveform visualisation placeholder, Play button, text input
- "Save All Names" CTA button at bottom — one click submits all
- No pagination — all unknowns on one screen

### Transcript View

- Left column: speaker name (bold, coloured per speaker — up to 6 distinct colours from accent palette)
- Right column: transcript text in JetBrains Mono
- Timestamps shown on hover
- No editing in v1 — read only

---

## Mobile Responsiveness

- Mobile app is native Android — no responsive concern
- Web UI must be usable on phone browser (for speaker naming on the go)
- Web UI responsive breakpoints:
  - Desktop (≥1024px): sidebar + main content
  - Tablet (768–1023px): stacked layout
  - Mobile (≤767px): single column, full-width table rows, bottom sheet for naming UI

---

## Reference Apps

| App | What to steal |
|-----|--------------|
| **Raycast** | Dark surface palette, compact information density, keyboard-first feel |
| **Obsidian** | Monospace transcript text, wikilink visual style, graph aesthetic |
| **Linear** | Status badge design, table row hover states, subtle border-only card style |
| **Voice Memos (iOS)** | Single-screen recorder simplicity, waveform animation — but darker |
