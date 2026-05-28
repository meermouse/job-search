# Model-Level Collision Design

**Date:** 2026-05-28
**Project:** tabletop-kit
**Branch:** feature/FE-004-pivot-base

## Problem

The current obstacle resolution in `clamp.ts` uses axis-aligned bounding boxes (AABB) for each unit, even when units are rotated. A unit at 45° has a larger AABB than its actual model footprint, so an approaching unit stops at the AABB corner rather than at the nearest actual model circle. The fix is to test collision at the individual model level.

Additionally, future unit types (cavalry on oval bases, vehicles, custom formations) will not fit the circular-models-on-rectangular-grid model, so the collision system needs to be designed for extensibility from the start.

---

## Architecture

Three files are affected:

| File | Change |
|---|---|
| `src/utils/obstacleResolution.ts` | **New.** All model-level collision logic, pixel space only |
| `src/utils/obstacleResolution.test.ts` | **New.** Replaces `collision.test.ts`; adds rotation cases |
| `src/utils/clamp.ts` | **Modified.** `resolveObstacles` replaced with thin % ↔ px wrapper; `Obstacle` type gains `modelCount` |
| `src/utils/collision.ts` | **Deleted** |
| `src/utils/collision.test.ts` | **Deleted** |

Board-edge clamping (rotated AABB) in `clamp.ts` is **unchanged** — it is correct and not related to this problem.

---

## `obstacleResolution.ts`

### Types

```typescript
export type Point = { x: number; y: number }

export type ModelShape =
  | { type: 'circle'; radius: number }
  // future: | { type: 'rect'; w: number; h: number }
  //         | { type: 'polygon'; vertices: Point[] }

export type PlacedModel = {
  center: Point    // pixel space
  shape: ModelShape
}
```

`ModelShape` is an extensible tagged union. Only `circle` is implemented now. Future shapes (rectangular cavalry bases, polygon vehicle footprints) add new variants without changing `resolveObstacles`.

### `getRotatedModels`

```typescript
export function getRotatedModels(
  topLeftPx: Point,
  unit: { rows: number; cols: number; modelCount: number; rotation?: number },
  baseDiamPx: number,
): PlacedModel[]
```

Computes the pixel-space center of each visible model (index < `modelCount`) after rotating the unit around its visual centre.

**Model centre before rotation (row, col):**
```
x = topLeft.x + col * (baseDiamPx + CIRCLE_GAP_PX) + baseDiamPx / 2
y = topLeft.y + row * baseDiamPx + baseDiamPx / 2
```

`CIRCLE_GAP_PX = 2` matches the horizontal gap in `.unit-token__row` CSS. There is no vertical gap between rows. This corrects a discrepancy in the old `getCircleCenters` which ignored the gap. The constant moves from `clamp.ts` to `obstacleResolution.ts`; after this change `clamp.ts` no longer references it.

**Rotation around unit centre:**
```
unitCx = topLeft.x + (cols * (baseDiamPx + CIRCLE_GAP_PX) - CIRCLE_GAP_PX) / 2
unitCy = topLeft.y + rows * baseDiamPx / 2
dx = center.x - unitCx
dy = center.y - unitCy
rotated.x = unitCx + dx*cosθ - dy*sinθ
rotated.y = unitCy + dx*sinθ + dy*cosθ
```

Returns `PlacedModel[]` with `{ type: 'circle', radius: baseDiamPx / 2 }` for each visible model.

**Rotation centre assumption:** `unitCy` uses `rows * baseDiamPx / 2`, which matches `transform-origin: 50% 50%` only if the `UnitToken` container height equals `rows * baseDiamPx` (i.e. the label is positioned outside the layout flow with `position: absolute`). Verify this during implementation by inspecting `UnitToken.css`.

### `resolveObstacles`

```typescript
export function resolveObstacles(
  desiredPx: Point,
  originPx: Point | null,
  draggedModels: PlacedModel[],
  obstacles: Array<{ models: PlacedModel[] }>,
): Point
```

Takes pre-computed `PlacedModel[]` for the dragged unit (at `desiredPx`) and each obstacle. Returns the adjusted `desiredPx` (top-left) that eliminates all model overlaps.

**The function is agnostic about how models were laid out.** This means any unit layout — grid, custom, vehicle — is supported by the caller providing different `PlacedModel[]` arrays.

**Push algorithm** (generalised from `collision.ts`):

1. Collect all colliding pairs `(a, b)` where `distance(a.center, b.center) < a.shape.radius + b.shape.radius`
2. If no collisions, return `desiredPx` unchanged
3. Compute push direction `d`:
   - If `originPx` is known: `d = normalize(originPx - desiredPx)` — push back toward origin
   - If `originPx` is null (sidebar drop): `d = normalize(a.center - b.center)` for first pair — push away from collision
4. For each colliding pair, solve the quadratic for minimum push distance `t`:
   ```
   Δ = a.center − b.center
   dot = Δ · d
   minSep = a.radius + b.radius
   disc = dot² − |Δ|² + minSep²
   t_pair = −dot + √disc
   ```
5. Return `desiredPx + max(t) * d`

The generalisation from the old code is `minSep = ra + rb` instead of `2r`, enabling different-sized models.

---

## `clamp.ts` changes

### `Obstacle` type gains `modelCount`

```typescript
export type Obstacle = {
  pos: { x: number; y: number }
  unit: { cols: number; rows: number; modelCount: number; rotation?: number }
}
```

`modelCount` is required so `getRotatedModels` knows which models are visible. Call sites in `App.tsx` already have the full unit object and need a one-line update per call site.

### `resolveObstacles` — thin % ↔ px wrapper

The new internal `resolveObstacles` in `clamp.ts`:

1. Converts `pos` from `%` → `px`: `posPx = { x: pos.x * boardWidthPx / 100, y: pos.y * boardHeightPx / 100 }`
2. Converts `prevPos` from `%` → `px` (or `null`)
3. Converts each obstacle `pos` from `%` → `px`
4. Calls `getRotatedModels` for the dragged unit at `posPx`
5. Calls `getRotatedModels` for each obstacle at its `px` position
6. Calls `resolveObstacles` from `obstacleResolution.ts`
7. Converts result from `px` → `%`

The AABB obstacle code (`getRotatedAABB`, overlap test, push logic) is removed entirely from `clamp.ts`.

---

## Testing

### `obstacleResolution.test.ts` (new)

**`getRotatedModels` tests:**
- Returns correct centres at rotation=0, including horizontal gap (distinguishes from old `getCircleCenters`)
- Returns correctly rotated centres at 90° and 45°
- Skips invisible models (index ≥ modelCount)

**`resolveObstacles` tests (migrated from `collision.test.ts`):**
- No collision → returns `desiredPx` unchanged
- Head-on push → circles at exactly touching distance after push
- Partial overlap with origin → pushed back along drag vector, circles touch
- Multi-unit scenario → single max-t push clears all collisions
- Sidebar placement (origin null) → pushed away from collision
- Zero-vector edge case → returned unchanged

**`resolveObstacles` tests (new — rotation cases):**
- Unit A at 45°, unit B approaching from the side: B stops at A's nearest model circle, not at A's AABB corner
- Both units rotated: collision detected at model level regardless of AABB overlap

### `clamp.test.ts` (updated)

Existing obstacle tests updated to add `modelCount` to each `Obstacle` shape (required by the new type). No new test logic — correctness of model-level collision is covered in `obstacleResolution.test.ts`.

### Deleted

`collision.ts` and `collision.test.ts` are deleted. All functionality is superseded by `obstacleResolution.ts`.
