# Unit Rotation Design

**Date:** 2026-05-28  
**Project:** tabletop-kit  
**Branch:** feature/FE-004-pivot-base  

## Overview

While dragging a unit on the board, scrolling the mouse wheel rotates it freely. On drop, the unit is placed at the angle shown by the ghost preview. Rotation is factored into the move log distance using the arc travelled by the furthest model.

---

## 1. Data Model

### `Unit` (types.ts)
Add `rotation: number` — degrees, default `0`. Persists on the server alongside `position`.

### `MoveLogEntry` (types.ts)
Add `fromRotation: number` and `toRotation: number` so undo/redo can restore rotation alongside position.

### `unit_moved` client message (useRoom.ts, server.ts)
Extend with:
- `rotation: number` — the final rotation angle in degrees
- `baseDiamPx: number` — the client's current base diameter in pixels
- `boardWidthPx: number` — the board's current pixel width; together with `baseDiamPx` the server derives `diamInches`

### Backward compatibility
Existing server-stored units won't have `rotation`. All server-side reads of `unit.rotation` must default to `0` (`unit.rotation ?? 0`). Same for `MoveLogEntry.fromRotation` / `toRotation`.

---

## 2. Rotation During Drag (App.tsx)

### State
```ts
const [draftRotation, setDraftRotation] = useState<number | null>(null)
const draftRotationRef = useRef<number | null>(null)
```
- Set to `unit.rotation ?? 0` on `dragStart` (both state and ref)
- Reset to `null` on `dragEnd` (both state and ref)
- On each wheel tick, update both: `draftRotationRef.current = next; setDraftRotation(next)`
- `handleDragEnd` reads from `draftRotationRef.current` (not state) to avoid stale-closure issues — mirrors the existing `unitsRef` pattern in App.tsx

### Wheel listener
A `useEffect` keyed on `activeUnit !== null` attaches/detaches a `wheel` listener on `document`:

```ts
const DEGREES_PER_PIXEL = 0.05  // ~5° per 100px scroll notch

function handleWheel(e: WheelEvent) {
  e.preventDefault()
  setDraftRotation(r => (r ?? 0) + e.deltaY * DEGREES_PER_PIXEL)
}
```

`preventDefault()` stops the page from scrolling during a drag.

### Ghost shape
```ts
type Ghost = { unit: Unit; position: { x: number; y: number }; rotation: number }
```
Set in `handleDragMove` using the current `draftRotation`.

### Rendering with rotation
| Element | Rotation applied |
|---|---|
| Ghost `<div>` in Board | `draftRotation` via `transform: rotate(Ndeg)` |
| `DragOverlay` wrapper | `draftRotation` via `transform: rotate(Ndeg)` |
| `DraggableToken` shadow (30% opacity) | `unit.rotation` (committed angle, unchanged during drag) |
| Opponent tokens | `unit.rotation` from server state |

CSS `transform: rotate()` defaults to rotating around the element's centre (`transform-origin: 50% 50%`), which matches the AABB centre used by the collision system.

---

## 3. Collision with Rotated AABB (clamp.ts)

### Updated signatures
```ts
// Unit shape gains rotation
type DraggedUnit = { cols: number; rows: number; rotation?: number }

// Obstacle gains rotation
type Obstacle = {
  pos: { x: number; y: number }
  unit: { cols: number; rows: number; rotation?: number }
}
```

### AABB computation
For a rectangle of pixel dimensions W × H, rotated by θ degrees, the AABB dimensions are:

```
aabbW = W·|cos θ| + H·|sin θ|
aabbH = W·|sin θ| + H·|cos θ|
```

The AABB is centred on the same centre as the unrotated rectangle:

```
centre = (pos.x + W%/2, pos.y + H%/2)    // in percentage coordinates
aabb_topLeft = (centre.x − aabbW%/2, centre.y − aabbH%/2)
```

A helper `getRotatedAABB(pos, cols, rows, diam, boardW, boardH, rotation)` returns `{ x, y, w, h }` in percentage coordinates.

### Board-edge clamping
Updated to use the AABB extent rather than the raw `cols × diam` / `rows × diam` dimensions, so a rotated unit never protrudes past the board edge.

### Obstacle overlap resolution
`resolveObstacles` computes the rotated AABB for both the dragged unit and each obstacle, then performs AABB overlap tests as before. The push vector is still computed from the drag direction or minimum penetration axis.

The return value of `clampPosition` remains `{ x, y }` in top-left percentage coordinates (same coordinate system as `unit.position`). AABB-centre ↔ top-left conversion is encapsulated inside `clamp.ts`.

---

## 4. Move Log — Rotation Arc Distance (server.ts, board.ts)

### Calculation
On `unit_moved`, the server calculates:

```
totalDistance = straight_line_distance + rotation_arc_distance
```

**Straight-line distance** — unchanged: Euclidean distance between `fromPosition` and `toPosition` in inches.

**Rotation arc distance** — the model furthest from the unit's centre traces the longest arc:

```
// For each visible model at grid position (row, col):
dx = (col + 0.5 − C/2) × diamInches
dy = (row + 0.5 − R/2) × diamInches
radius = √(dx² + dy²)

maxRadius = max(radius) across all visible models

Δθ_rad = (toRotation − fromRotation) × π / 180
arcInches = maxRadius × |Δθ_rad|
```

The client sends `baseDiamPx` and `boardWidthPx` in the `unit_moved` message. The server derives:

```
diamInches = baseDiamPx / (boardWidthPx / BOARD_WIDTH_INCHES)
```

The combined total is stored in `MoveLogEntry.distanceInches` and displayed as one number in the log (no UI changes to MoveLog.tsx required).

### Undo/redo
`MoveLogEntry.fromRotation` and `toRotation` allow the server to restore the correct angle when undoing or redoing a move, mirroring the existing position undo logic.

---

## Files Changed

| File | Change |
|---|---|
| `src/types.ts` | Add `rotation` to `Unit`; add `fromRotation`, `toRotation` to `MoveLogEntry` |
| `src/hooks/useRoom.ts` | Extend `unit_moved` SendMessage with `rotation`, `baseDiamPx`, `boardWidthPx` |
| `src/App.tsx` | Add `draftRotation` state, document wheel listener, pass rotation to ghost and DragOverlay |
| `src/components/Board.tsx` | Apply `rotation` from ghost; apply `unit.rotation` to opponent tokens |
| `src/components/DraggableToken.tsx` | Apply `unit.rotation` to shadow div |
| `src/utils/clamp.ts` | Add `rotation` to unit/obstacle types; implement rotated AABB in clamping and obstacle resolution |
| `src/utils/board.ts` | Add `calcRotationArcInches` helper |
| `src/party/server.ts` | Extend `unit_moved` handler to save rotation, compute arc distance, include `fromRotation`/`toRotation` in log entry; update undo/redo to restore rotation |
