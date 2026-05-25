# Map Selection Feature — Design Spec

**Date:** 2026-05-25  
**Project:** tabletop-kit  
**Status:** Approved

---

## Overview

Add a map selection modal to the tabletop-kit app. Users click a "Map" button in the top bar to open a gallery of map images organised by season. Selecting a map replaces the plain green board background with the chosen image. Map images live in `src/assets/maps/{season}/` subfolders and are discovered automatically at build time using Vite's `import.meta.glob`.

---

## Requirements

- A "Map" button in the top bar opens a full-screen modal gallery.
- The modal organises maps into tabs, one per season subfolder (e.g. `season-2` → "Season 2").
- Each tab shows a thumbnail grid — thumbnail image above, prettified name below.
- Clicking a thumbnail selects the map, closes the modal, and sets it as the board background.
- Once a map is selected it stays. There is no "clear" or "reset to green" option.
- New season subfolders added to `src/assets/maps/` appear automatically with no code changes.
- If no maps are found, the modal shows a "No maps available" message.

---

## Architecture & Data Flow

### Asset Discovery

A new utility `src/utils/maps.ts` uses Vite's eager glob to discover all map assets at build time:

```ts
const modules = import.meta.glob('/src/assets/maps/**/*.webp', { as: 'url', eager: true })
```

This produces a plain `Record<string, string>` of `{ filePath → resolvedUrl }`. The utility parses each path into a structured `MapEntry` and groups entries by season.

```ts
type MapEntry = { name: string; url: string }
// Returns: { 'season-2': [...], 'season-3': [...], ... }
export function getMapsBySeason(): Record<string, MapEntry[]>
```

**Path parsing rules:**
- Season: last folder segment before the filename (e.g. `season-2`). Displayed as "Season 2" (replace `-` with space, title-case).
- Map name: filename without extension, camelCase split on uppercase letters (e.g. `BattlelinesDrawn` → `Battlelines Drawn`).

### State

`App.tsx` owns one new piece of state:

```ts
const [selectedMap, setSelectedMap] = useState<string | null>(null)
const [isMapPickerOpen, setIsMapPickerOpen] = useState(false)
```

`selectedMap` is a resolved URL string (or `null` for the default green board). It is passed to `Board` as a prop. `isMapPickerOpen` controls whether the `MapPicker` modal is rendered.

### Data flow

```
App
 ├─ TopBar  ←  "Map" button → setIsMapPickerOpen(true)
 ├─ Board   ←  mapUrl prop  → inline background-image style
 └─ MapPicker (when open)
       ├─ receives mapsBySeason (computed once at module load)
       └─ onSelect(url) → setSelectedMap(url); setIsMapPickerOpen(false)
```

---

## Components

### `src/utils/maps.ts` (new)

Pure utility — no React. Runs `import.meta.glob` at module initialisation. Exports `getMapsBySeason()`. Can be unit-tested by mocking the glob result.

### `src/components/MapPicker.tsx` (new)

Props:
```ts
type Props = {
  mapsBySeason: Record<string, MapEntry[]>
  onSelect: (url: string) => void
  onClose: () => void
}
```

Renders:
- Full-viewport semi-transparent backdrop. Click → `onClose()` (no map change).
- Centred white card (max ~800 × 600px, scrollable internally).
- Tab row at top — one tab per season key, sorted alphabetically. Active tab highlighted.
- Thumbnail grid for the active season. Each tile: `<img>` thumbnail + name text below.
  - Clicking a tile → `onSelect(url)`.
- "No maps available" message when `mapsBySeason` is empty.

### `src/components/MapPicker.css` (new)

Styles for backdrop, card, tab row, thumbnail grid, and tile. Tiles use `overflow: hidden; text-overflow: ellipsis` on the name. Grid scrolls internally; tab row is sticky within the card.

### `src/components/TopBar.tsx` (modified)

Adds a "Map" button. Positioned on the right side of the bar, before the trashcan drop zone. Calls `onOpenMapPicker` prop (new).

### `src/components/Board.tsx` (modified)

Gains `mapUrl: string | null` prop. When non-null, applies:
```tsx
style={{ backgroundImage: `url(${mapUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
```
as an inline style on the `.board` div. When null, no inline style — CSS green (`#4a7c3f`) applies as normal.

### `src/App.tsx` (modified)

- Add `selectedMap` and `isMapPickerOpen` state.
- Pass `onOpenMapPicker={() => setIsMapPickerOpen(true)}` to `TopBar`.
- Pass `mapUrl={selectedMap}` to `Board`.
- Render `<MapPicker>` when `isMapPickerOpen` is true.

---

## Edge Cases

| Case | Behaviour |
|---|---|
| No maps in assets | Modal shows "No maps available", no tabs |
| Single season | Single tab rendered (no special-casing) |
| Long map name | Truncated with ellipsis in tile label |
| Many maps in a season | Thumbnail grid scrolls; tabs stay fixed |
| Backdrop click | Modal closes, no map change |
| Map already selected | Opening modal again shows same grid; user can pick a different map |

---

## Testing

`getMapsBySeason()` is a pure function — unit-testable with a mocked glob object:

1. Path parsing: verify `season-2/BattlelinesDrawn.webp` → `{ season: 'season-2', name: 'Battlelines Drawn', url: '<mocked-url>' }`.
2. Grouping: verify multiple paths group correctly by season key.

No component tests added (consistent with existing test scope — utilities only).

---

## Files Changed

| File | Change |
|---|---|
| `src/utils/maps.ts` | New — glob discovery + path parsing |
| `src/components/MapPicker.tsx` | New — modal gallery component |
| `src/components/MapPicker.css` | New — modal styles |
| `src/components/TopBar.tsx` | Add "Map" button + `onOpenMapPicker` prop |
| `src/components/Board.tsx` | Add `mapUrl` prop, apply as background-image |
| `src/App.tsx` | Add state, wire up MapPicker |

No changes to: `types.ts`, `LeftPanel`, `UnitToken`, `DraggableToken`, `clamp.ts`, `colors.ts`, `unitNames.ts`.
