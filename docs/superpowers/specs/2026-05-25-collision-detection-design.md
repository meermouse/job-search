# Collision Detection & Resolution — Design Spec

**Date:** 2026-05-25  
**Project:** tabletop-kit  
**Status:** Approved

---

## Overview

When a unit is dragged on the board (either from the left panel onto the board, or repositioned on the board), collision is detected at the level of individual circular model bases. If the dragged unit's circles overlap any placed unit's circles, the dragged unit is pushed back toward its drag origin until all overlaps are cleared. A semi-transparent ghost appears on the board at the resolved landing position during the drag, so the user can see where the unit will settle before releasing.

---

## Requirements

- Collision is detected per model base (circle), not per bounding box.
- Only visible bases (index < `modelCount`) participate in collision.
- When a collision is detected during drag, the unit is pushed back along the drag vector (toward its stored position) until all overlapping pairs are cleared.
- For initial placement from the sidebar (no stored position), the unit is pushed away from the colliding unit along the overlap vector.
- While dragging over a collision, a semi-transparent ghost renders on the board at the resolved position.
- The ghost only appears when a collision is active (resolved position ≠ desired position). No ghost when the path is clear.
- On drop, the unit is placed at the resolved position — the same position the ghost showed.
- The DragOverlay (floating unit following cursor) is unaffected — it continues to follow the cursor normally.
- No ghost shown when hovering over the trashcan.

---

## Architecture & Data Flow

### New file

**`src/utils/collision.ts`** — pure math, no React. Exports `getCircleCenters` and `resolveCollision`. All positions in pixels (board-relative). The caller converts from/to board-relative percentages.

### Modified files

**`src/App.tsx`**
- New state: `ghost: { unit: Unit; position: { x: number; y: number } } | null`
- New handler: `handleDragMove` (wired to `onDragMove` on `DndContext`)
- Updated: `handleDragEnd` — calls `resolveCollision` so the stored position matches the ghost
- `ghost` cleared in `handleDragStart` and `handleDragEnd`

**`src/components/Board.tsx`**
- New prop: `ghost?: { unit: Unit; position: { x: number; y: number } } | null`
- Renders a `.board-ghost` wrapper (pointer-events: none, opacity: 0.45, z-index: 1) containing a `UnitToken` at `ghost.position` when set

### New test file

**`src/utils/collision.test.ts`** — 6 unit tests for the pure functions.

---

## Collision Algorithm

### `getCircleCenters(topLeft, unit, baseDiamPx)`

```ts
type Point = { x: number; y: number }

export function getCircleCenters(
  topLeft: Point,
  unit: { rows: number; cols: number; modelCount: number },
  baseDiamPx: number
): Point[]
```

Iterates `rows × cols` bases. For each index `i = row * cols + col` where `i < modelCount`, yields center:

```
{ x: topLeft.x + col * baseDiamPx + baseDiamPx / 2,
  y: topLeft.y + row * baseDiamPx + baseDiamPx / 2 }
```

### `resolveCollision(desired, origin, dragged, others, radius)`

```ts
export function resolveCollision(
  desired: Point,
  origin: Point | null,
  dragged: { rows: number; cols: number; modelCount: number },
  others: Array<{ position: Point; rows: number; cols: number; modelCount: number }>,
  radius: number   // baseDiamPx / 2
): Point
```

**Step 1 — push direction `d`:**
- If `origin` is provided and `|desired − origin| > 0.5`: `d = normalize(origin − desired)` (toward drag origin)
- If `origin` is null or `desired ≈ origin`: find the first colliding pair `(A, B)` and set `d = normalize(A − B)` (away from the placed circle). If no collision exists, return `desired`.

**Step 2 — gather overlapping pairs:**
Compute `getCircleCenters` for the dragged unit at `desired` and for each unit in `others` at their stored positions. Collect every pair `(A, B)` where `|A − B| < 2r`.

If no pairs: return `desired` immediately.

**Step 3 — solve per pair:**
For each colliding pair `(A, B)`, solve for the minimum `t ≥ 0` along direction `d` such that `|A + t·d − B| = 2r`:

```
let Δ = A − B
let dot = Δ · d            // dot product
let disc = dot² − |Δ|² + 4r²
if disc < 0: skip (no intersection along this ray)
t_pair = −dot + √disc
```

**Step 4 — take max t:**
`t = max(t_pair)` across all colliding pairs.

**Step 5 — return resolved position:**
`return { x: desired.x + t * d.x, y: desired.y + t * d.y }`

The caller clamps the result to board boundaries after this call.

---

## App.tsx Integration

### `handleDragMove`

Wired to `onDragMove` on `DndContext`. Fires on every pointer move during a drag.

```
1. If event.over?.id !== 'board': setGhost(null); return
2. Find unit from event.active.id
3. Compute desiredPct:
   - Repositioning (unit.position !== null): unit.position + delta converted to %
   - Sidebar drag (unit.position === null): activeRect position relative to boardRect
4. clampPosition(desiredPct, unit, baseDiamPx, boardW, boardH)
5. Convert desiredPct → desiredPx (multiply by boardW/boardH / 100)
6. originPx = unit.position ? convert(unit.position) : null
7. othersPx = placed units excluding dragged unit, with positions in px
8. resolvedPx = resolveCollision(desiredPx, originPx, unit, othersPx, baseDiamPx / 2)
9. resolvedPct = convert back to %
10. finalPct = clampPosition(resolvedPct, ...)
11. If |resolvedPx − desiredPx| > 0.5: setGhost({ unit, position: finalPct })
    Else: setGhost(null)
```

### `handleDragEnd` update

After computing `rawPos` from `delta`, run the same collision resolution steps (5–10 above) before calling `setUnits`. The stored position must match the ghost the user saw.

For the initial placement path (unit.position === null), run the same resolution using `originPx = null`.

---

## Ghost Rendering

In `Board.tsx`:

```tsx
{ghost && (
  <div
    className="board-ghost"
    style={{
      position: 'absolute',
      left: `${ghost.position.x}%`,
      top: `${ghost.position.y}%`,
      pointerEvents: 'none',
    }}
  >
    <UnitToken unit={ghost.unit} baseDiamPx={baseDiamPx} />
  </div>
)}
```

In `Board.css`:

```css
.board-ghost {
  opacity: 0.45;
  z-index: 1;
}
```

---

## Edge Cases

| Case | Behaviour |
|---|---|
| No collision | Ghost not shown; unit drops at clamped desired position |
| Collision resolved position hits board edge | Clamp wins — unit stays on board even if still touching |
| `desired ≈ origin` (unit barely moved) | `d` is zero vector → return `desired` unchanged |
| Dragged over trashcan | Ghost hidden; trashcan glow behaviour unchanged |
| Unit with modelCount < rows × cols | Only visible circles participate; invisible grid slots ignored |
| Multi-unit collision | Single `max(t)` push clears all collisions in one step |

---

## Testing

`src/utils/collision.test.ts` — 6 tests, all pure function calls, no DOM:

1. **No collision** — two units far apart: returns `desired` unchanged.
2. **Head-on push** — dragged unit centred on placed unit, origin directly left: resolved position has nearest circles exactly touching (`|A−B| = baseDiamPx`).
3. **Partial overlap** — dragged unit clipping one edge: resolves with minimum push along drag vector.
4. **Multi-unit** — placed units on both sides with a gap; dragged from left: resolves into the gap.
5. **Sidebar placement (origin = null)** — collision detected; resolves away from placed unit along overlap vector.
6. **Zero drag vector** — `desired === origin`: returns `desired` unchanged.

---

## Files Changed

| File | Change |
|---|---|
| `src/utils/collision.ts` | New — `getCircleCenters`, `resolveCollision` |
| `src/utils/collision.test.ts` | New — 6 unit tests |
| `src/App.tsx` | Add `ghost` state, `handleDragMove`, update `handleDragEnd` |
| `src/components/Board.tsx` | Add `ghost` prop, render `.board-ghost` |
| `src/components/Board.css` | Add `.board-ghost` styles |

No changes to: `types.ts`, `TopBar`, `LeftPanel`, `UnitToken`, `DraggableToken`, `MapPicker`, `clamp.ts`, `colors.ts`, `unitNames.ts`, `maps.ts`.
