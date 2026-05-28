# Model-Level Collision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace AABB obstacle collision in `clamp.ts` with model-level circle collision so units stop at the actual model circles rather than the rectangular bounding box, and lay the foundation for non-circular model shapes.

**Architecture:** A new `obstacleResolution.ts` works entirely in pixel space with an extensible `ModelShape` union type. `clamp.ts` becomes a thin % ↔ px wrapper that calls the new file for obstacle resolution; board-edge AABB clamping is unchanged. `collision.ts` and its tests are deleted — their functionality is superseded by the new file.

**Tech Stack:** TypeScript, Vitest

**Spec correction vs design doc:** The design doc stated "no vertical gap between rows." The actual CSS (`.unit-token { gap: 2px; flex-direction: column }`) applies a 2px gap both between rows AND between columns. The implementation and tests below use the correct symmetric gap.

---

## File Structure

| File | Change |
|---|---|
| `src/utils/obstacleResolution.ts` | **Create** — `ModelShape`, `PlacedModel`, `getRotatedModels`, `resolveObstacles` |
| `src/utils/obstacleResolution.test.ts` | **Create** — all model-level collision tests |
| `src/utils/clamp.ts` | **Modify** — `Obstacle` type gains `modelCount`; `resolveObstacles` becomes a % ↔ px wrapper; `CIRCLE_GAP_PX` and AABB obstacle code removed |
| `src/utils/clamp.test.ts` | **Modify** — add `modelCount` to obstacle shapes |
| `src/utils/collision.ts` | **Delete** |
| `src/utils/collision.test.ts` | **Delete** |
| `src/App.tsx` | **Modify** — add `modelCount` to `othersPct` in `handleDragMove` and `handleDragEnd` |

---

## Task 1: Create `obstacleResolution.ts` with types and `getRotatedModels` (TDD)

**Files:**
- Create: `src/utils/obstacleResolution.ts`
- Create: `src/utils/obstacleResolution.test.ts`

- [ ] **Step 1: Create the test file with failing `getRotatedModels` tests**

Create `src/utils/obstacleResolution.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { getRotatedModels } from './obstacleResolution'

describe('getRotatedModels', () => {
  const diam = 20

  it('returns correct centre for a 1×1 unit at rotation 0', () => {
    const models = getRotatedModels({ x: 0, y: 0 }, { rows: 1, cols: 1, modelCount: 1 }, diam)
    expect(models).toHaveLength(1)
    expect(models[0].center).toEqual({ x: 10, y: 10 })
    expect(models[0].shape).toEqual({ type: 'circle', radius: 10 })
  })

  // With gap=2, col centres are col*(diam+2)+diam/2: col0=10, col1=32
  // Old getCircleCenters (no gap) would give col0=10, col1=30 — this test distinguishes them
  it('applies horizontal and vertical gap of 2px between models', () => {
    const models = getRotatedModels({ x: 0, y: 0 }, { rows: 2, cols: 2, modelCount: 4 }, diam)
    expect(models[0].center).toEqual({ x: 10, y: 10 })  // row0 col0
    expect(models[1].center).toEqual({ x: 32, y: 10 })  // row0 col1
    expect(models[2].center).toEqual({ x: 10, y: 32 })  // row1 col0
    expect(models[3].center).toEqual({ x: 32, y: 32 })  // row1 col1
  })

  it('skips invisible models (index >= modelCount)', () => {
    const models = getRotatedModels({ x: 0, y: 0 }, { rows: 1, cols: 2, modelCount: 1 }, diam)
    expect(models).toHaveLength(1)
    expect(models[0].center).toEqual({ x: 10, y: 10 })
  })

  // 2×1 unit at 90°:
  //   unitCx = (2*(20+2)-2)/2 = 21, unitCy = (1*(20+2)-2)/2 = 10
  //   col0 unrotated (10,10): dx=-11,dy=0 → at 90° cos=0,sin=1 → (21, 10-11) = (21,-1)
  //   col1 unrotated (32,10): dx=11,dy=0  → at 90°            → (21, 10+11) = (21,21)
  it('rotates model centres around the unit visual centre at 90°', () => {
    const models = getRotatedModels({ x: 0, y: 0 }, { rows: 1, cols: 2, modelCount: 2, rotation: 90 }, diam)
    expect(models[0].center.x).toBeCloseTo(21)
    expect(models[0].center.y).toBeCloseTo(-1)
    expect(models[1].center.x).toBeCloseTo(21)
    expect(models[1].center.y).toBeCloseTo(21)
  })

  it('offsets correctly when topLeft is non-zero', () => {
    const at0 = getRotatedModels({ x: 0, y: 0 }, { rows: 1, cols: 1, modelCount: 1 }, diam)
    const at100 = getRotatedModels({ x: 100, y: 200 }, { rows: 1, cols: 1, modelCount: 1 }, diam)
    expect(at100[0].center.x).toBeCloseTo(at0[0].center.x + 100)
    expect(at100[0].center.y).toBeCloseTo(at0[0].center.y + 200)
  })
})
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd c:/Code/tabletop-kit && npm test
```

Expected: `getRotatedModels is not a function` or similar import error.

- [ ] **Step 3: Create `obstacleResolution.ts` with types and `getRotatedModels`**

Create `src/utils/obstacleResolution.ts`:

```typescript
export type Point = { x: number; y: number }

export type ModelShape =
  | { type: 'circle'; radius: number }

export type PlacedModel = {
  center: Point
  shape: ModelShape
}

// CSS gap between model circles: 2px both horizontally (.unit-token__row gap)
// and vertically (.unit-token flex column gap)
const CIRCLE_GAP_PX = 2

export function getRotatedModels(
  topLeftPx: Point,
  unit: { rows: number; cols: number; modelCount: number; rotation?: number },
  baseDiamPx: number,
): PlacedModel[] {
  const rotation = unit.rotation ?? 0
  const θ = (rotation * Math.PI) / 180
  const cosθ = Math.cos(θ)
  const sinθ = Math.sin(θ)

  const step = baseDiamPx + CIRCLE_GAP_PX
  // Visual centre of the model grid (label height ignored — same approximation as clamp.ts AABB)
  const unitCx = topLeftPx.x + (unit.cols * step - CIRCLE_GAP_PX) / 2
  const unitCy = topLeftPx.y + (unit.rows * step - CIRCLE_GAP_PX) / 2

  const models: PlacedModel[] = []
  for (let row = 0; row < unit.rows; row++) {
    for (let col = 0; col < unit.cols; col++) {
      if (row * unit.cols + col >= unit.modelCount) continue

      const cx = topLeftPx.x + col * step + baseDiamPx / 2
      const cy = topLeftPx.y + row * step + baseDiamPx / 2
      const dx = cx - unitCx
      const dy = cy - unitCy

      models.push({
        center: {
          x: unitCx + dx * cosθ - dy * sinθ,
          y: unitCy + dx * sinθ + dy * cosθ,
        },
        shape: { type: 'circle', radius: baseDiamPx / 2 },
      })
    }
  }
  return models
}
```

- [ ] **Step 4: Run and confirm pass**

```bash
npm test
```

Expected: all 5 new `getRotatedModels` tests pass plus all existing tests.

- [ ] **Step 5: Commit**

```bash
cd c:/Code/tabletop-kit && git add src/utils/obstacleResolution.ts src/utils/obstacleResolution.test.ts && git commit -m "feat: add getRotatedModels to obstacleResolution"
```

---

## Task 2: Add `resolveObstacles` to `obstacleResolution.ts` (TDD)

**Files:**
- Modify: `src/utils/obstacleResolution.ts`
- Modify: `src/utils/obstacleResolution.test.ts`

- [ ] **Step 1: Add failing tests**

Append to `src/utils/obstacleResolution.test.ts`:

```typescript
import { resolveObstacles } from './obstacleResolution'

describe('resolveObstacles', () => {
  const diam = 32
  const radius = 16

  function unit1x1(topLeft: Point) {
    return getRotatedModels(topLeft, { rows: 1, cols: 1, modelCount: 1 }, diam)
  }

  it('returns desiredPx unchanged when no collision', () => {
    const dragged = unit1x1({ x: 0, y: 0 })
    const obs = unit1x1({ x: 200, y: 0 })
    expect(resolveObstacles({ x: 0, y: 0 }, { x: 0, y: 0 }, dragged, [{ models: obs }]))
      .toEqual({ x: 0, y: 0 })
  })

  it('pushes head-on collision to exactly touching distance', () => {
    // Dragged and placed overlap exactly; origin far left → push left
    const dragged = unit1x1({ x: 0, y: 0 })
    const obs = unit1x1({ x: 0, y: 0 })
    const result = resolveObstacles({ x: 0, y: 0 }, { x: -200, y: 0 }, dragged, [{ models: obs }])
    const a = { x: result.x + radius, y: result.y + radius }
    const b = { x: radius, y: radius }
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeCloseTo(2 * radius, 5)
  })

  it('resolves partial overlap — pushed back along drag vector', () => {
    // Dragged at x=10 overlaps placed at x=0; origin far left
    const dragged = unit1x1({ x: 10, y: 0 })
    const obs = unit1x1({ x: 0, y: 0 })
    const result = resolveObstacles({ x: 10, y: 0 }, { x: -100, y: 0 }, dragged, [{ models: obs }])
    const a = { x: result.x + radius, y: result.y + radius }
    const b = { x: radius, y: radius }
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeCloseTo(2 * radius, 5)
    expect(result.x).toBeLessThan(10)  // pushed back (leftward)
  })

  it('clears all collisions in a multi-unit scenario', () => {
    // Dragged at x=16 overlaps both a left unit (x=0) and a right unit (x=32)
    const dragged = unit1x1({ x: 16, y: 0 })
    const left = unit1x1({ x: 0, y: 0 })
    const right = unit1x1({ x: 32, y: 0 })
    const result = resolveObstacles({ x: 16, y: 0 }, { x: -100, y: 0 }, dragged,
      [{ models: left }, { models: right }])
    const a = { x: result.x + radius, y: result.y + radius }
    const bl = { x: radius, y: radius }
    const br = { x: 32 + radius, y: radius }
    expect(Math.hypot(a.x - bl.x, a.y - bl.y)).toBeGreaterThanOrEqual(2 * radius - 0.01)
    expect(Math.hypot(a.x - br.x, a.y - br.y)).toBeGreaterThanOrEqual(2 * radius - 0.01)
  })

  it('resolves sidebar placement (originPx null) — pushes away from collision', () => {
    const dragged = unit1x1({ x: 10, y: 0 })
    const obs = unit1x1({ x: 0, y: 0 })
    const result = resolveObstacles({ x: 10, y: 0 }, null, dragged, [{ models: obs }])
    const a = { x: result.x + radius, y: result.y + radius }
    const b = { x: radius, y: radius }
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeCloseTo(2 * radius, 5)
    expect(result.x).toBeGreaterThan(10)  // pushed away (rightward)
  })

  it('returns desiredPx unchanged when drag vector is zero and models exactly overlap', () => {
    const dragged = unit1x1({ x: 10, y: 0 })
    const obs = unit1x1({ x: 10, y: 0 })
    // desiredPx === originPx → zero vector; model centres overlap → pLen < 1e-9 guard fires
    expect(resolveObstacles({ x: 10, y: 0 }, { x: 10, y: 0 }, dragged, [{ models: obs }]))
      .toEqual({ x: 10, y: 0 })
  })

  it('ignores invisible models (index >= modelCount)', () => {
    // 1×2 dragged but only modelCount=1; placed unit aligned to overlap only the invisible model
    const diam16 = 16
    const r16 = 8
    const dragged = getRotatedModels({ x: -5, y: 0 }, { rows: 1, cols: 2, modelCount: 1 }, diam16)
    // visible model at (-5+8, 8) = (3, 8). Placed circle at (32+8, 8) = (40, 8). Distance = 37 > 16 → no collision
    const obs = getRotatedModels({ x: 32, y: 0 }, { rows: 1, cols: 1, modelCount: 1 }, diam16)
    expect(resolveObstacles({ x: -5, y: 0 }, { x: -100, y: 0 }, dragged, [{ models: obs }]))
      .toEqual({ x: -5, y: 0 })
  })

  // Unit A (2×1 at 90°) at topLeft (100,0):
  //   models at (121,-1) and (121,21) per getRotatedModels computation
  // Unit B (1×1) desired topLeft (111,5): model centre (121,15)
  //   overlaps both A models → gets pushed right toward origin (200,5)
  //   after push: B model centre at touching distance from nearest A model
  it('stops at model circle edge for rotated unit, not AABB corner', () => {
    const diam20 = 20
    const obsModels = getRotatedModels({ x: 100, y: 0 },
      { rows: 1, cols: 2, modelCount: 2, rotation: 90 }, diam20)
    const draggedModels = getRotatedModels({ x: 111, y: 5 },
      { rows: 1, cols: 1, modelCount: 1 }, diam20)
    const result = resolveObstacles({ x: 111, y: 5 }, { x: 200, y: 5 }, draggedModels, [{ models: obsModels }])
    // B's model centre after push
    const bCenter = { x: result.x + 10, y: result.y + 10 }
    const distToA0 = Math.hypot(bCenter.x - obsModels[0].center.x, bCenter.y - obsModels[0].center.y)
    const distToA1 = Math.hypot(bCenter.x - obsModels[1].center.x, bCenter.y - obsModels[1].center.y)
    // nearest A model must be at exactly touching distance (20 = r+r)
    expect(Math.min(distToA0, distToA1)).toBeCloseTo(20, 0)
  })
})
```

- [ ] **Step 2: Run and confirm failure**

```bash
npm test
```

Expected: `resolveObstacles is not a function`.

- [ ] **Step 3: Implement `resolveObstacles` in `obstacleResolution.ts`**

Add to `src/utils/obstacleResolution.ts` (append after `getRotatedModels`):

```typescript
function getRadius(shape: ModelShape): number {
  return shape.radius  // only 'circle' exists; add cases here when new shapes arrive
}

export function resolveObstacles(
  desiredPx: Point,
  originPx: Point | null,
  draggedModels: PlacedModel[],
  obstacles: Array<{ models: PlacedModel[] }>,
): Point {
  // Collect all colliding pairs
  const pairs: Array<{ a: PlacedModel; b: PlacedModel }> = []
  for (const obs of obstacles) {
    for (const a of draggedModels) {
      for (const b of obs.models) {
        const minSep = getRadius(a.shape) + getRadius(b.shape)
        if (Math.hypot(a.center.x - b.center.x, a.center.y - b.center.y) < minSep) {
          pairs.push({ a, b })
        }
      }
    }
  }

  if (pairs.length === 0) return desiredPx

  // Compute push direction d
  const dx = originPx ? originPx.x - desiredPx.x : 0
  const dy = originPx ? originPx.y - desiredPx.y : 0
  const len = Math.hypot(dx, dy)

  const MIN_DRAG_PX = 0.5
  let d: Point
  if (len > MIN_DRAG_PX) {
    d = { x: dx / len, y: dy / len }
  } else {
    const { a, b } = pairs[0]
    const pLen = Math.hypot(a.center.x - b.center.x, a.center.y - b.center.y)
    if (pLen < 1e-9) return desiredPx
    d = {
      x: (a.center.x - b.center.x) / pLen,
      y: (a.center.y - b.center.y) / pLen,
    }
  }

  // Quadratic solve per pair: find max t such that |Δ + t·d| = minSep
  let t = 0
  for (const { a, b } of pairs) {
    const Δx = a.center.x - b.center.x
    const Δy = a.center.y - b.center.y
    const dot = Δx * d.x + Δy * d.y
    const minSep = getRadius(a.shape) + getRadius(b.shape)
    const disc = dot * dot - (Δx * Δx + Δy * Δy) + minSep * minSep
    if (disc < 0) continue
    const tPair = -dot + Math.sqrt(disc)
    if (tPair > t) t = tPair
  }

  return { x: desiredPx.x + t * d.x, y: desiredPx.y + t * d.y }
}
```

- [ ] **Step 4: Fix the import in the test file**

The test file imports `getRotatedModels` from the first describe block. Ensure the import at the top covers both functions:

```typescript
import { getRotatedModels, resolveObstacles, type Point } from './obstacleResolution'
```

- [ ] **Step 5: Run and confirm all tests pass**

```bash
npm test
```

Expected: all new tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/utils/obstacleResolution.ts src/utils/obstacleResolution.test.ts && git commit -m "feat: add resolveObstacles to obstacleResolution"
```

---

## Task 3: Wire `obstacleResolution.ts` into `clamp.ts`; delete `collision.ts`

**Files:**
- Modify: `src/utils/clamp.ts`
- Modify: `src/utils/clamp.test.ts`
- Delete: `src/utils/collision.ts`
- Delete: `src/utils/collision.test.ts`

- [ ] **Step 1: Update `clamp.test.ts` — add `modelCount` to obstacle shapes**

In `src/utils/clamp.test.ts`, the `clampPosition — obstacle avoidance` describe block declares:

```typescript
const unitA = { cols: 2, rows: 2 }
const unitB = { cols: 2, rows: 2 }
const obsB = { pos: { x: 50, y: 50 }, unit: unitB }
```

Change to:

```typescript
const unitA = { cols: 2, rows: 2, modelCount: 4 }
const unitB = { cols: 2, rows: 2, modelCount: 4 }
const obsB = { pos: { x: 50, y: 50 }, unit: unitB }
```

Also update the two test calls that pass `unitA` inline as the dragged unit shape (second argument to `clampPosition`). Grep for `{ cols: 2, rows: 2 }` in the file — add `modelCount: 4` to each occurrence.

- [ ] **Step 2: Run and confirm clamp.test.ts fails (TypeScript error)**

```bash
npm test
```

Expected: TypeScript compile error — `Obstacle.unit` is missing `modelCount`.

- [ ] **Step 3: Rewrite `clamp.ts`**

Replace the entire contents of `src/utils/clamp.ts` with:

```typescript
import { getRotatedModels, resolveObstacles as resolveModelCollision } from './obstacleResolution'

export type Obstacle = {
  pos: { x: number; y: number }
  unit: { cols: number; rows: number; modelCount: number; rotation?: number }
}

/**
 * Returns the axis-aligned bounding box (in % coords) of a rectangle
 * with pre-computed percentage dimensions rotated around its centre.
 */
function getRotatedAABB(
  pos: { x: number; y: number },
  wPct: number,
  hPct: number,
  rotationDeg: number,
): { x: number; y: number; w: number; h: number } {
  const θ = (rotationDeg * Math.PI) / 180
  const cos = Math.abs(Math.cos(θ))
  const sin = Math.abs(Math.sin(θ))
  const aabbW = wPct * cos + hPct * sin
  const aabbH = wPct * sin + hPct * cos
  const cx = pos.x + wPct / 2
  const cy = pos.y + hPct / 2
  return { x: cx - aabbW / 2, y: cy - aabbH / 2, w: aabbW, h: aabbH }
}

export function clampPosition(
  pos: { x: number; y: number },
  unit: { cols: number; rows: number; modelCount: number; rotation?: number },
  baseDiamPx: number,
  boardWidthPx: number,
  boardHeightPx: number,
  prevPos?: { x: number; y: number } | null,
  obstacles?: Obstacle[],
): { x: number; y: number } {
  const rotation = unit.rotation ?? 0
  const W = (unit.cols * baseDiamPx / boardWidthPx) * 100
  const H = (unit.rows * baseDiamPx / boardHeightPx) * 100
  const { w: aabbW, h: aabbH } = getRotatedAABB({ x: 0, y: 0 }, W, H, rotation)

  const minX = aabbW / 2 - W / 2
  const maxX = 100 - W / 2 - aabbW / 2
  const minY = aabbH / 2 - H / 2
  const maxY = 100 - H / 2 - aabbH / 2

  let result = {
    x: Math.max(minX, Math.min(pos.x, maxX)),
    y: Math.max(minY, Math.min(pos.y, maxY)),
  }

  if (obstacles && obstacles.length > 0) {
    result = resolveObstaclesPct(result, prevPos ?? null, unit, obstacles, baseDiamPx, boardWidthPx, boardHeightPx)
  }

  return result
}

function resolveObstaclesPct(
  pos: { x: number; y: number },
  prevPos: { x: number; y: number } | null,
  unit: { cols: number; rows: number; modelCount: number; rotation?: number },
  obstacles: Obstacle[],
  baseDiamPx: number,
  boardWidthPx: number,
  boardHeightPx: number,
): { x: number; y: number } {
  const toPx = (p: { x: number; y: number }) => ({
    x: p.x * boardWidthPx / 100,
    y: p.y * boardHeightPx / 100,
  })
  const toPct = (p: { x: number; y: number }) => ({
    x: p.x * 100 / boardWidthPx,
    y: p.y * 100 / boardHeightPx,
  })

  const posPx = toPx(pos)
  const prevPosPx = prevPos ? toPx(prevPos) : null

  const draggedModels = getRotatedModels(posPx, unit, baseDiamPx)
  const obstacleData = obstacles.map(obs => ({
    models: getRotatedModels(toPx(obs.pos), obs.unit, baseDiamPx),
  }))

  return toPct(resolveModelCollision(posPx, prevPosPx, draggedModels, obstacleData))
}
```

- [ ] **Step 4: Run and confirm tests pass**

```bash
npm test
```

The two existing obstacle tests in `clamp.test.ts` will fail with new expected values because model-level collision stops units where circles touch, not where AABB edges touch. Update them:

**"clamps unit A just above unit B when entering from the top"** — change `expect(result.y).toBeCloseTo(40)` to:
```typescript
expect(result.y).toBeCloseTo(50.5, 0)
```
_(A's row-0 models are at y=230px, B's row-1 models are at y=232px, overlap=2px, push=18px upward → final topLeft y = 202/400×100 = 50.5%)_

**"clamps unit A to the left of unit B when entering perfectly from the left"** — change `expect(result.x).toBeCloseTo(39.5)` to:
```typescript
expect(result.x).toBeCloseTo(45)
```
_(A and B overlap completely; push direction=left, t=20px → final topLeft x = 180/400×100 = 45%)_

Also update the test description strings to reflect the new semantic ("circles touching" rather than "AABB edge touching").

- [ ] **Step 5: Delete `collision.ts` and `collision.test.ts`**

```bash
cd c:/Code/tabletop-kit && rm src/utils/collision.ts src/utils/collision.test.ts
```

- [ ] **Step 6: Run tests and TypeScript check**

```bash
npm test && npx tsc --noEmit
```

Expected: all tests pass, no compile errors.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: replace AABB obstacle collision with model-level circle collision"
```

---

## Task 4: Update `App.tsx` call sites to add `modelCount`

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Update `handleDragMove` othersPct map**

In `src/App.tsx`, find the `handleDragMove` function. Change:

```typescript
const othersPct = units
  .filter(u => u.position !== null && u.id !== unit.id)
  .map(u => ({ pos: u.position!, unit: { cols: u.cols, rows: u.rows, rotation: u.rotation ?? 0 } }))
```

To:

```typescript
const othersPct = units
  .filter(u => u.position !== null && u.id !== unit.id)
  .map(u => ({ pos: u.position!, unit: { cols: u.cols, rows: u.rows, modelCount: u.modelCount, rotation: u.rotation ?? 0 } }))
```

- [ ] **Step 2: Update `handleDragEnd` othersPct map**

In `src/App.tsx`, find the `handleDragEnd` function. Change:

```typescript
const othersPct = unitsRef.current
  .filter(u => u.position !== null && u.id !== unit.id)
  .map(u => ({ pos: u.position!, unit: { cols: u.cols, rows: u.rows, rotation: u.rotation ?? 0 } }))
```

To:

```typescript
const othersPct = unitsRef.current
  .filter(u => u.position !== null && u.id !== unit.id)
  .map(u => ({ pos: u.position!, unit: { cols: u.cols, rows: u.rows, modelCount: u.modelCount, rotation: u.rotation ?? 0 } }))
```

- [ ] **Step 3: Also update `clampPosition` dragged-unit argument**

In both `handleDragMove` and `handleDragEnd`, `clampPosition` is called with `{ ...unit, rotation }` as the second argument. Since `Unit` now has `modelCount`, the spread already includes it — no change needed. Verify by running tsc.

- [ ] **Step 4: Compile check and run tests**

```bash
npx tsc --noEmit && npm test
```

Expected: no errors, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/App.tsx && git commit -m "feat: pass modelCount in obstacle descriptors from App.tsx"
```

---

## Self-Review Checklist

- [ ] `getRotatedModels` applies both horizontal AND vertical `CIRCLE_GAP_PX = 2` gap
- [ ] `resolveObstacles` uses `ra + rb` for minimum separation (not hardcoded `2r`)
- [ ] `collision.ts` and `collision.test.ts` are deleted
- [ ] `clamp.ts` has no more `CIRCLE_GAP_PX` constant (moved to `obstacleResolution.ts`)
- [ ] `clamp.test.ts` obstacle tests have `modelCount` in both dragged unit and `Obstacle.unit`
- [ ] Both `othersPct` maps in `App.tsx` include `modelCount`
- [ ] All tests pass (`npm test`)
- [ ] TypeScript compiles (`npx tsc --noEmit`)
