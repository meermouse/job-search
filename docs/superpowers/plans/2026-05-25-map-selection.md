# Map Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a modal map picker that lets users browse season-organised `.webp` map images and apply one as the board background.

**Architecture:** Map assets are discovered at build time via Vite's `import.meta.glob`. A pure utility (`maps.ts`) parses glob results into season-grouped entries. `App` owns `selectedMap` and `isMapPickerOpen` state; a new `MapPicker` modal consumes the grouped data and returns a selected URL; `Board` applies the URL as a CSS `background-image`.

**Tech Stack:** React 19, TypeScript, Vite (`import.meta.glob`), plain CSS, Vitest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/utils/maps.ts` | Create | Glob discovery + path parsing, exports `MapEntry` type, `parseGlobResult`, `getMapsBySeason` |
| `src/utils/maps.test.ts` | Create | Unit tests for `parseGlobResult` |
| `src/components/MapPicker.tsx` | Create | Modal gallery: tab row per season, thumbnail grid |
| `src/components/MapPicker.css` | Create | Modal styles |
| `src/components/TopBar.tsx` | Modify | Add `onOpenMapPicker` prop + Map button |
| `src/components/TopBar.css` | Modify | Style the Map button |
| `src/components/Board.tsx` | Modify | Add `mapUrl` prop, apply as `background-image` |
| `src/App.tsx` | Modify | Add `selectedMap` / `isMapPickerOpen` state, wire MapPicker |

---

## Task 1: `src/utils/maps.ts` — asset discovery utility (TDD)

**Files:**
- Create: `src/utils/maps.test.ts`
- Create: `src/utils/maps.ts`

- [ ] **Step 1: Write failing tests**

Create `src/utils/maps.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { parseGlobResult } from './maps'

describe('parseGlobResult', () => {
  it('parses a single path into the correct season and name', () => {
    const result = parseGlobResult({
      '/src/assets/maps/season-2/BattlelinesDrawn.webp': 'http://localhost/BattlelinesDrawn.webp',
    })
    expect(result['season-2']).toHaveLength(1)
    expect(result['season-2'][0]).toEqual({
      name: 'Battlelines Drawn',
      url: 'http://localhost/BattlelinesDrawn.webp',
    })
  })

  it('groups entries by season', () => {
    const result = parseGlobResult({
      '/src/assets/maps/season-2/MapA.webp': 'url-a',
      '/src/assets/maps/season-3/MapB.webp': 'url-b',
      '/src/assets/maps/season-2/MapC.webp': 'url-c',
    })
    expect(Object.keys(result).sort()).toEqual(['season-2', 'season-3'])
    expect(result['season-2']).toHaveLength(2)
    expect(result['season-3']).toHaveLength(1)
  })

  it('sorts entries within a season alphabetically by name', () => {
    const result = parseGlobResult({
      '/src/assets/maps/season-2/Zebra.webp': 'url-z',
      '/src/assets/maps/season-2/Alpha.webp': 'url-a',
    })
    expect(result['season-2'][0].name).toBe('Alpha')
    expect(result['season-2'][1].name).toBe('Zebra')
  })

  it('returns an empty object when given empty input', () => {
    expect(parseGlobResult({})).toEqual({})
  })
})
```

- [ ] **Step 2: Run tests — expect failures**

```bash
npm test -- maps.test
```

Expected: 4 failures (`parseGlobResult` not defined).

- [ ] **Step 3: Implement `src/utils/maps.ts`**

Create `src/utils/maps.ts`:

```ts
export type MapEntry = { name: string; url: string }

function camelToWords(str: string): string {
  return str.replace(/([A-Z])/g, ' $1').trim()
}

export function parseGlobResult(modules: Record<string, string>): Record<string, MapEntry[]> {
  const result: Record<string, MapEntry[]> = {}
  for (const [path, url] of Object.entries(modules)) {
    const parts = path.split('/')
    const filename = parts[parts.length - 1]
    const season = parts[parts.length - 2]
    const name = camelToWords(filename.replace(/\.webp$/, ''))
    if (!result[season]) result[season] = []
    result[season].push({ name, url })
  }
  for (const entries of Object.values(result)) {
    entries.sort((a, b) => a.name.localeCompare(b.name))
  }
  return result
}

const globbed = import.meta.glob('/src/assets/maps/**/*.webp', {
  query: '?url',
  import: 'default',
  eager: true,
}) as Record<string, string>

export function getMapsBySeason(): Record<string, MapEntry[]> {
  return parseGlobResult(globbed)
}
```

- [ ] **Step 4: Run tests — expect 4 passing**

```bash
npm test -- maps.test
```

Expected: 4 passing. (The existing 12 tests should still pass — run `npm test` to confirm.)

- [ ] **Step 5: Commit**

```bash
git add src/utils/maps.ts src/utils/maps.test.ts
git commit -m "feat: add maps utility with glob discovery and path parsing"
```

---

## Task 2: `MapPicker` component

**Files:**
- Create: `src/components/MapPicker.tsx`
- Create: `src/components/MapPicker.css`

- [ ] **Step 1: Create `src/components/MapPicker.tsx`**

```tsx
import { useState } from 'react'
import './MapPicker.css'
import type { MapEntry } from '../utils/maps'

type Props = {
  mapsBySeason: Record<string, MapEntry[]>
  onSelect: (url: string) => void
  onClose: () => void
}

export default function MapPicker({ mapsBySeason, onSelect, onClose }: Props) {
  const seasons = Object.keys(mapsBySeason).sort()
  const [activeTab, setActiveTab] = useState(seasons[0] ?? '')

  function seasonLabel(key: string): string {
    return key.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }

  if (seasons.length === 0) {
    return (
      <div className="map-picker-backdrop" onClick={onClose}>
        <div className="map-picker-card" onClick={e => e.stopPropagation()}>
          <p className="map-picker-empty">No maps available</p>
        </div>
      </div>
    )
  }

  const entries = mapsBySeason[activeTab] ?? []

  return (
    <div className="map-picker-backdrop" onClick={onClose}>
      <div className="map-picker-card" onClick={e => e.stopPropagation()}>
        <div className="map-picker-tabs">
          {seasons.map(season => (
            <button
              key={season}
              className={`map-picker-tab${season === activeTab ? ' map-picker-tab--active' : ''}`}
              onClick={() => setActiveTab(season)}
            >
              {seasonLabel(season)}
            </button>
          ))}
        </div>
        <div className="map-picker-grid">
          {entries.map(entry => (
            <button
              key={entry.url}
              className="map-picker-tile"
              onClick={() => onSelect(entry.url)}
            >
              <img src={entry.url} alt={entry.name} className="map-picker-thumb" />
              <span className="map-picker-name">{entry.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `src/components/MapPicker.css`**

```css
.map-picker-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.map-picker-card {
  background: #fff;
  border-radius: 8px;
  width: min(800px, 95vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.map-picker-tabs {
  display: flex;
  border-bottom: 1px solid #ddd;
  flex-shrink: 0;
  padding: 0 8px;
}

.map-picker-tab {
  padding: 10px 20px;
  border: none;
  border-bottom: 3px solid transparent;
  background: none;
  cursor: pointer;
  font-size: 14px;
  color: #555;
  margin-bottom: -1px;
}

.map-picker-tab--active {
  color: #222;
  border-bottom-color: #4a7c3f;
  font-weight: 600;
}

.map-picker-tab:hover:not(.map-picker-tab--active) {
  color: #333;
  background: #f5f5f5;
}

.map-picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
  padding: 16px;
  overflow-y: auto;
}

.map-picker-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  border: 2px solid transparent;
  border-radius: 6px;
  padding: 6px;
  background: none;
  cursor: pointer;
  gap: 6px;
  transition: border-color 0.1s, background 0.1s;
}

.map-picker-tile:hover {
  border-color: #4a7c3f;
  background: #f0f7ee;
}

.map-picker-thumb {
  width: 100%;
  aspect-ratio: 112 / 153;
  object-fit: cover;
  border-radius: 4px;
}

.map-picker-name {
  font-size: 11px;
  text-align: center;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #333;
}

.map-picker-empty {
  padding: 48px;
  text-align: center;
  color: #888;
  font-size: 15px;
}
```

- [ ] **Step 3: Run existing tests to ensure nothing broken**

```bash
npm test
```

Expected: all existing tests still passing.

- [ ] **Step 4: Commit**

```bash
git add src/components/MapPicker.tsx src/components/MapPicker.css
git commit -m "feat: add MapPicker modal component"
```

---

## Task 3: Add Map button to `TopBar`

**Files:**
- Modify: `src/components/TopBar.tsx`
- Modify: `src/components/TopBar.css`

- [ ] **Step 1: Update `TopBar.tsx`**

Replace the entire file content with:

```tsx
import { useState } from 'react'
import { useDroppable } from '@dnd-kit/core'
import './TopBar.css'

type FormState = {
  name: string
  rows: number
  cols: number
  modelCount: number
}

type Props = {
  onAddUnit: (form: FormState) => void
  isTrashOver: boolean
  onOpenMapPicker: () => void
}

export default function TopBar({ onAddUnit, isTrashOver, onOpenMapPicker }: Props) {
  const { setNodeRef: setTrashRef } = useDroppable({ id: 'trashcan' })
  const [name, setName] = useState('')
  const [rows, setRows] = useState(2)
  const [cols, setCols] = useState(5)
  const [modelCount, setModelCount] = useState(10)

  function handleRowsChange(val: number) {
    const r = Math.max(1, Math.min(4, val))
    setRows(r)
    setModelCount(Math.min(modelCount, r * cols))
  }

  function handleColsChange(val: number) {
    const c = Math.max(1, Math.min(10, val))
    setCols(c)
    setModelCount(Math.min(modelCount, rows * c))
  }

  function handleAdd() {
    onAddUnit({ name, rows, cols, modelCount })
    setName('')
  }

  return (
    <div className="top-bar">
      <div className="top-bar__field">
        <label>Name</label>
        <input
          className="top-bar__input top-bar__input--name"
          type="text"
          placeholder="auto"
          value={name}
          onChange={e => setName(e.target.value)}
        />
      </div>
      <div className="top-bar__field">
        <label>Rows</label>
        <input
          className="top-bar__input top-bar__input--number"
          type="number"
          min={1}
          max={4}
          value={rows}
          onChange={e => handleRowsChange(Number(e.target.value))}
        />
      </div>
      <div className="top-bar__field">
        <label>Cols</label>
        <input
          className="top-bar__input top-bar__input--number"
          type="number"
          min={1}
          max={10}
          value={cols}
          onChange={e => handleColsChange(Number(e.target.value))}
        />
      </div>
      <div className="top-bar__field">
        <label>Models</label>
        <input
          className="top-bar__input top-bar__input--number"
          type="number"
          min={1}
          max={rows * cols}
          value={modelCount}
          onChange={e => setModelCount(Math.max(1, Math.min(rows * cols, Number(e.target.value))))}
        />
      </div>
      <button className="top-bar__add-btn" onClick={handleAdd}>+ Add Unit</button>
      <button className="top-bar__map-btn" onClick={onOpenMapPicker}>Map</button>
      <div
        ref={setTrashRef}
        className={`top-bar__trash${isTrashOver ? ' top-bar__trash--over' : ''}`}
      >
        🗑
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Update `TopBar.css`**

Add these rules at the end of the file (after the existing `.top-bar__trash--over` block), and remove `margin-left: auto` from `.top-bar__trash`:

Replace the entire file with:

```css
.top-bar {
  height: 52px;
  background: #16213e;
  border-bottom: 1px solid #0f3460;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  flex-shrink: 0;
}

.top-bar__field {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #a0a0b0;
}

.top-bar__input {
  background: #0f3460;
  border: 1px solid #2a4080;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 4px 8px;
  font-size: 13px;
}

.top-bar__input--name {
  width: 120px;
}

.top-bar__input--number {
  width: 48px;
}

.top-bar__add-btn {
  background: #27ae60;
  border: none;
  border-radius: 4px;
  color: white;
  font-size: 13px;
  font-weight: bold;
  padding: 5px 14px;
  cursor: pointer;
}

.top-bar__add-btn:hover {
  background: #2ecc71;
}

.top-bar__map-btn {
  margin-left: auto;
  background: #0f3460;
  border: 1px solid #2a4080;
  border-radius: 4px;
  color: #a0a0b0;
  font-size: 13px;
  padding: 5px 14px;
  cursor: pointer;
}

.top-bar__map-btn:hover {
  background: #2a4080;
  color: #e0e0e0;
}

.top-bar__trash {
  font-size: 22px;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: default;
  transition: background 0.15s, color 0.15s;
}

.top-bar__trash--over {
  background: #c0392b;
  color: white;
}
```

- [ ] **Step 3: Run existing tests**

```bash
npm test
```

Expected: all tests passing (TopBar has no unit tests — the TypeScript compiler will catch prop errors at build time).

- [ ] **Step 4: Commit**

```bash
git add src/components/TopBar.tsx src/components/TopBar.css
git commit -m "feat: add Map button to TopBar"
```

---

## Task 4: Add `mapUrl` prop to `Board`

**Files:**
- Modify: `src/components/Board.tsx`

- [ ] **Step 1: Update `Board.tsx`**

Replace the entire file with:

```tsx
import { forwardRef } from 'react'
import { useDroppable } from '@dnd-kit/core'
import './Board.css'
import type { Unit } from '../types'
import DraggableToken from './DraggableToken'

type Props = {
  units: Unit[]
  baseDiamPx: number
  mapUrl: string | null
}

const Board = forwardRef<HTMLDivElement, Props>(function Board({ units, baseDiamPx, mapUrl }, ref) {
  const { setNodeRef } = useDroppable({ id: 'board' })
  const placed = units.filter(u => u.position !== null)

  return (
    <div className="board-wrapper">
      <div
        className="board"
        style={mapUrl ? { backgroundImage: `url(${mapUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}
        ref={(el) => {
          setNodeRef(el)
          if (typeof ref === 'function') ref(el)
          else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = el
        }}
      >
        {placed.map(unit => (
          <DraggableToken
            key={unit.id}
            unit={unit}
            baseDiamPx={baseDiamPx}
          />
        ))}
      </div>
    </div>
  )
})

export default Board
```

- [ ] **Step 2: Run existing tests**

```bash
npm test
```

Expected: all tests passing.

- [ ] **Step 3: Commit**

```bash
git add src/components/Board.tsx
git commit -m "feat: add mapUrl prop to Board for background-image support"
```

---

## Task 5: Wire everything together in `App.tsx`

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Update `App.tsx`**

Replace the entire file with:

```tsx
import { useLayoutEffect, useRef, useState } from 'react'
import {
  DndContext,
  type DragEndEvent,
  type DragStartEvent,
  type DragOverEvent,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import './App.css'
import TopBar from './components/TopBar'
import LeftPanel from './components/LeftPanel'
import Board from './components/Board'
import UnitToken from './components/UnitToken'
import MapPicker from './components/MapPicker'
import type { Unit } from './types'
import { assignColor } from './utils/colors'
import { generateName } from './utils/unitNames'
import { clampPosition } from './utils/clamp'
import { getMapsBySeason } from './utils/maps'

const mapsBySeason = getMapsBySeason()

export default function App() {
  const boardRef = useRef<HTMLDivElement>(null)
  const [units, setUnits] = useState<Unit[]>([])
  const [activeUnit, setActiveUnit] = useState<Unit | null>(null)
  const [isTrashOver, setIsTrashOver] = useState(false)
  const [baseDiamPx, setBaseDiamPx] = useState(18)
  const [selectedMap, setSelectedMap] = useState<string | null>(null)
  const [isMapPickerOpen, setIsMapPickerOpen] = useState(false)
  const nextColorIndex = useRef(0)

  useLayoutEffect(() => {
    const el = boardRef.current
    if (!el) return
    const update = () => setBaseDiamPx((el.offsetWidth / 1120) * 32)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const sensors = useSensors(useSensor(PointerSensor, {
    activationConstraint: { distance: 4 },
  }))

  function handleAddUnit(form: { name: string; rows: number; cols: number; modelCount: number }) {
    const usedNames = units.map(u => u.name)
    const name = form.name.trim() || generateName(usedNames)
    const color = assignColor(nextColorIndex.current++)
    const newUnit: Unit = {
      id: crypto.randomUUID(),
      name,
      color,
      rows: form.rows,
      cols: form.cols,
      modelCount: form.modelCount,
      position: null,
    }
    setUnits(prev => [...prev, newUnit])
  }

  function handleDragStart(event: DragStartEvent) {
    const unit = units.find(u => u.id === event.active.id) ?? null
    setActiveUnit(unit)
    setIsTrashOver(false)
  }

  function handleDragOver(event: DragOverEvent) {
    const unit = units.find(u => u.id === event.active.id)
    if (!unit || unit.position === null) return
    setIsTrashOver(event.over?.id === 'trashcan')
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveUnit(null)
    setIsTrashOver(false)

    const { active, over, delta } = event
    if (!over) return

    const unit = units.find(u => u.id === active.id)
    if (!unit) return

    const board = boardRef.current
    if (!board) return

    const boardW = board.offsetWidth
    const boardH = board.offsetHeight
    const diam = (boardW / 1120) * 32
    setBaseDiamPx(diam)

    if (over.id === 'trashcan' && unit.position !== null) {
      setUnits(prev => prev.filter(u => u.id !== unit.id))
      return
    }

    if (over.id === 'board') {
      if (unit.position === null) {
        const boardRect = board.getBoundingClientRect()
        const activeRect = (active.rect.current as { translated: DOMRect | null }).translated
        if (!activeRect) return
        const rawX = ((activeRect.left - boardRect.left) / boardW) * 100
        const rawY = ((activeRect.top - boardRect.top) / boardH) * 100
        const pos = clampPosition({ x: rawX, y: rawY }, unit, diam, boardW, boardH)
        setUnits(prev => prev.map(u => u.id === unit.id ? { ...u, position: pos } : u))
      } else {
        const deltaXPct = (delta.x / boardW) * 100
        const deltaYPct = (delta.y / boardH) * 100
        const rawPos = { x: unit.position.x + deltaXPct, y: unit.position.y + deltaYPct }
        const pos = clampPosition(rawPos, unit, diam, boardW, boardH)
        setUnits(prev => prev.map(u => u.id === unit.id ? { ...u, position: pos } : u))
      }
    }
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div className="app">
        <TopBar
          onAddUnit={handleAddUnit}
          isTrashOver={isTrashOver}
          onOpenMapPicker={() => setIsMapPickerOpen(true)}
        />
        <div className="app-body">
          <LeftPanel units={units} />
          <Board ref={boardRef} units={units} baseDiamPx={baseDiamPx} mapUrl={selectedMap} />
        </div>
      </div>
      <DragOverlay>
        {activeUnit && <UnitToken unit={activeUnit} baseDiamPx={baseDiamPx || 18} />}
      </DragOverlay>
      {isMapPickerOpen && (
        <MapPicker
          mapsBySeason={mapsBySeason}
          onSelect={(url) => { setSelectedMap(url); setIsMapPickerOpen(false) }}
          onClose={() => setIsMapPickerOpen(false)}
        />
      )}
    </DndContext>
  )
}
```

- [ ] **Step 2: Run full test suite**

```bash
npm test
```

Expected: all tests passing (16 total: 12 original + 4 new maps tests).

- [ ] **Step 3: TypeScript check**

```bash
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/App.tsx
git commit -m "feat: wire map selection state and MapPicker into App"
```

---

## Task 6: Smoke test in browser

**Files:** none (manual verification only)

- [ ] **Step 1: Start dev server**

```bash
npm run dev
```

Open the URL shown (usually `http://localhost:5173`).

- [ ] **Step 2: Verify Map button**

Check the top bar has a "Map" button to the right of "+ Add Unit", with the trashcan after it.

- [ ] **Step 3: Open the modal**

Click "Map". Confirm:
- Semi-transparent backdrop covers the whole screen.
- A white card appears, centred.
- "Season 2" tab is visible and active.
- 12 map thumbnails are shown in a grid, each with a prettified name below.

- [ ] **Step 4: Select a map**

Click any thumbnail. Confirm:
- Modal closes.
- The board background changes from green to the selected map image, filling the board area (`cover` sizing).
- Units already on the board remain positioned correctly over the map.

- [ ] **Step 5: Re-open and change map**

Click "Map" again, pick a different map. Confirm the board updates to the new selection.

- [ ] **Step 6: Backdrop close**

Open the modal, click the dark backdrop outside the card. Confirm the modal closes without changing the map.

- [ ] **Step 7: Production build check**

```bash
npm run build
```

Expected: build succeeds with no errors. (Vite bundles the `import.meta.glob` references at build time.)

- [ ] **Step 8: Final commit if anything was tweaked during smoke test**

```bash
git add -p
git commit -m "fix: smoke test corrections for map selection"
```

(Skip this step if nothing needed adjusting.)
