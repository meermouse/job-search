# Unit Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While dragging a unit on the board, scrolling the mouse wheel freely rotates it; on drop the unit is placed at the angle shown by the ghost; collision uses the rotated AABB; the move log distance includes the arc travelled by the furthest model.

**Architecture:** `rotation: number` (degrees) is added to `Unit` and restored on undo/redo via `fromRotation`/`toRotation` on `MoveLogEntry`. During drag, `draftRotation` state + a parallel `draftRotationRef` (to avoid stale closure on dragEnd) track the live angle; a document-level `wheel` listener updates both. The server computes arc distance from `baseDiamPx` and `boardWidthPx` included in the `unit_moved` message. Collision uses the AABB of the rotated rectangle centred on the unit's visual centre.

**Tech Stack:** React 18, TypeScript, @dnd-kit/core, Vitest, PartyKit

---

## File Structure

| File | Change |
|---|---|
| `src/types.ts` | Add `rotation` to `Unit`; add `fromRotation`, `toRotation` to `MoveLogEntry` |
| `src/hooks/useRoom.ts` | Add `rotation`, `baseDiamPx`, `boardWidthPx` (all optional) to `unit_moved` SendMessage |
| `src/utils/board.ts` | Add `calcRotationArcInches` |
| `src/utils/board.test.ts` | Tests for `calcRotationArcInches` |
| `src/utils/clamp.ts` | Add `rotation?` to unit/obstacle types; add `getRotatedAABB` helper; use rotated AABB in board-edge clamping and obstacle resolution |
| `src/utils/clamp.test.ts` | Tests for rotated AABB board clamping |
| `src/party/server.ts` | Save `rotation` on unit; compute total distance including arc; store `fromRotation`/`toRotation` in log entry; restore rotation in undo/redo |
| `src/party/server.test.ts` | Tests for rotation save, arc distance, undo/redo restoring rotation |
| `src/components/DraggableToken.tsx` | Apply `unit.rotation` CSS transform to shadow div |
| `src/App.tsx` | Add `draftRotation` state + `draftRotationRef`; document wheel listener; pass rotation to ghost and DragOverlay; pass rotation to `clampPosition` |
| `src/components/Board.tsx` | Apply `ghost.rotation` to ghost div; apply `unit.rotation` to opponent token divs |

---

## Task 1: Extend data types

**Files:**
- Modify: `src/types.ts`
- Modify: `src/hooks/useRoom.ts`

- [ ] **Step 1: Add `rotation` to `Unit` and `fromRotation`/`toRotation` to `MoveLogEntry`**

In `src/types.ts`, apply these changes:

```typescript
export type Unit = {
  id: string
  name: string
  color: string
  rows: number
  cols: number
  modelCount: number
  position: { x: number; y: number } | null
  rotation: number          // degrees, 0 by default
  ownerId: string
}

export type MoveLogEntry = {
  id: string
  unitId: string
  unitName: string
  unitColor: string
  playerId: string
  fromPosition: { x: number; y: number } | null
  toPosition: { x: number; y: number }
  fromRotation: number      // degrees
  toRotation: number        // degrees
  distanceInches: number
  timestamp: number
  active: boolean
}
```

- [ ] **Step 2: Extend `unit_moved` SendMessage**

In `src/hooks/useRoom.ts`, change the `unit_moved` variant of `SendMessage`:

```typescript
export type SendMessage =
  | { type: 'unit_added'; name: string; rows: number; cols: number; modelCount: number }
  | { type: 'unit_moved'; unitId: string; position: { x: number; y: number }; rotation?: number; baseDiamPx?: number; boardWidthPx?: number }
  | { type: 'unit_deleted'; unitId: string }
  | { type: 'unit_undo' }
  | { type: 'unit_redo' }
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Fix any type errors before continuing (they will mostly be "Property 'rotation' is missing" complaints on object literals — add `rotation: 0` where needed).

- [ ] **Step 4: Commit**

```bash
git add src/types.ts src/hooks/useRoom.ts
git commit -m "feat: add rotation field to Unit and MoveLogEntry types"
```

---

## Task 2: `calcRotationArcInches` (board.ts, TDD)

**Files:**
- Modify: `src/utils/board.ts`
- Modify: `src/utils/board.test.ts`

- [ ] **Step 1: Write failing tests**

Append to `src/utils/board.test.ts`:

```typescript
import { calcRotationArcInches } from './board'

describe('calcRotationArcInches', () => {
  // A 1×1 unit has its single model at the centre — radius = 0, arc is always 0
  it('returns 0 for a single-model unit regardless of rotation', () => {
    expect(calcRotationArcInches({ rows: 1, cols: 1, modelCount: 1 }, 90, 1)).toBe(0)
  })

  // 0° delta → no rotation arc
  it('returns 0 when delta rotation is 0', () => {
    expect(calcRotationArcInches({ rows: 1, cols: 2, modelCount: 2 }, 0, 1)).toBe(0)
  })

  // 2×1 unit (2 cols, 1 row), diam = 1 inch:
  //   model centres at (-0.5", 0) and (+0.5", 0) relative to unit centre
  //   maxRadius = 0.5"
  //   360° = 2π rad → arc = 0.5 × 2π ≈ 3.1416"
  it('calculates arc for a 2×1 unit rotated 360°', () => {
    const arc = calcRotationArcInches({ rows: 1, cols: 2, modelCount: 2 }, 360, 1)
    expect(arc).toBeCloseTo(Math.PI, 4)   // 0.5 × 2π = π
  })

  // 2×2 unit, diam = 1 inch:
  //   corner model at (-0.5", -0.5") → radius = √0.5 ≈ 0.7071"
  //   180° = π rad → arc = √0.5 × π ≈ 2.2214"
  it('calculates arc for a 2×2 unit rotated 180°', () => {
    const arc = calcRotationArcInches({ rows: 2, cols: 2, modelCount: 4 }, 180, 1)
    expect(arc).toBeCloseTo(Math.sqrt(0.5) * Math.PI, 4)
  })

  // Partial modelCount: only visible models are considered
  // 2×2 unit with modelCount=1 — only (row=0, col=0) is visible → radius = √0.5, same as corner
  it('only considers visible models when computing maxRadius', () => {
    const full = calcRotationArcInches({ rows: 2, cols: 2, modelCount: 4 }, 90, 1)
    const partial = calcRotationArcInches({ rows: 2, cols: 2, modelCount: 1 }, 90, 1)
    // modelCount=1 means only (0,0) is visible — same corner radius as full unit
    expect(partial).toBeCloseTo(full, 4)
  })
})
```

- [ ] **Step 2: Run and confirm failure**

```bash
npm test
```

Expected: `calcRotationArcInches is not a function` or similar.

- [ ] **Step 3: Implement `calcRotationArcInches` in `src/utils/board.ts`**

```typescript
export function calcRotationArcInches(
  unit: { rows: number; cols: number; modelCount: number },
  deltaRotationDeg: number,
  diamInches: number,
): number {
  if (deltaRotationDeg === 0) return 0

  let maxRadius = 0
  for (let row = 0; row < unit.rows; row++) {
    for (let col = 0; col < unit.cols; col++) {
      if (row * unit.cols + col >= unit.modelCount) continue
      const dx = (col + 0.5 - unit.cols / 2) * diamInches
      const dy = (row + 0.5 - unit.rows / 2) * diamInches
      const r = Math.sqrt(dx * dx + dy * dy)
      if (r > maxRadius) maxRadius = r
    }
  }

  const deltaRad = Math.abs(deltaRotationDeg) * (Math.PI / 180)
  return maxRadius * deltaRad
}
```

- [ ] **Step 4: Run and confirm pass**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/utils/board.ts src/utils/board.test.ts
git commit -m "feat: add calcRotationArcInches to board utils"
```

---

## Task 3: Rotated AABB in `clamp.ts` (TDD)

**Files:**
- Modify: `src/utils/clamp.ts`
- Modify: `src/utils/clamp.test.ts`

- [ ] **Step 1: Write failing tests for rotated board-edge clamping**

Append to the `describe('clampPosition — board bounds', ...)` block in `src/utils/clamp.test.ts`:

```typescript
  // 3-col × 1-row unit, diam=20px, board=400×400px, rotation=90°:
  //   Unrotated: W=60px=15%, H=20px=5%
  //   At 90°: aabbW = 15×|cos90|+5×|sin90| = 5%, aabbH = 15×|sin90|+5×|cos90| = 15%
  //   AABB centre offset from pos: (7.5%, 2.5%)
  //   Board constraints on pos.x: [aabbW/2 - W/2, 100 - W/2 - aabbW/2] = [-5, 90]
  //   Board constraints on pos.y: [aabbH/2 - H/2, 100 - H/2 - aabbH/2] = [5, 90]

  it('uses rotated AABB for board clamping — clamps max x/y at 90°', () => {
    const result = clampPosition(
      { x: 99, y: 99 },
      { cols: 3, rows: 1, rotation: 90 },
      20, 400, 400,
    )
    expect(result.x).toBeCloseTo(90)
    expect(result.y).toBeCloseTo(90)
  })

  it('uses rotated AABB for board clamping — clamps min y at 90° (AABB top protrudes)', () => {
    // At rotation=90 and pos.y=0, AABB top = 0 + 2.5 - 7.5 = -5% → clamp to pos.y=5
    const result = clampPosition(
      { x: 0, y: 0 },
      { cols: 3, rows: 1, rotation: 90 },
      20, 400, 400,
    )
    expect(result.x).toBeCloseTo(0)   // AABB left = 0 + 7.5 - 2.5 = 5% > 0, no x clamp
    expect(result.y).toBeCloseTo(5)
  })

  it('rotation=0 behaves identically to the unrotated case (backward compat)', () => {
    const withRotation = clampPosition({ x: 99, y: 99 }, { cols: 2, rows: 1, rotation: 0 }, 20, 400, 600)
    const without = clampPosition({ x: 99, y: 99 }, { cols: 2, rows: 1 }, 20, 400, 600)
    expect(withRotation.x).toBeCloseTo(without.x)
    expect(withRotation.y).toBeCloseTo(without.y)
  })
```

- [ ] **Step 2: Run and confirm failure**

```bash
npm test
```

Expected: the two rotated tests fail (clamping ignores rotation).

- [ ] **Step 3: Implement rotated AABB in `src/utils/clamp.ts`**

Replace the entire file with:

```typescript
export type Obstacle = {
  pos: { x: number; y: number }
  unit: { cols: number; rows: number; rotation?: number }
}

// Matches gap: 2px in .unit-token__row — the horizontal space between model circles
const CIRCLE_GAP_PX = 2

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
  unit: { cols: number; rows: number; rotation?: number },
  baseDiamPx: number,
  boardWidthPx: number,
  boardHeightPx: number,
  prevPos?: { x: number; y: number } | null,
  obstacles?: Obstacle[],
): { x: number; y: number } {
  const rotation = unit.rotation ?? 0
  const W = (unit.cols * baseDiamPx / boardWidthPx) * 100
  const H = (unit.rows * baseDiamPx / boardHeightPx) * 100
  const θ = (rotation * Math.PI) / 180
  const cos = Math.abs(Math.cos(θ))
  const sin = Math.abs(Math.sin(θ))
  const aabbW = W * cos + H * sin
  const aabbH = W * sin + H * cos

  // Clamping constraints on pos (top-left of unrotated rect) so AABB stays on board
  const minX = aabbW / 2 - W / 2
  const maxX = 100 - W / 2 - aabbW / 2
  const minY = aabbH / 2 - H / 2
  const maxY = 100 - H / 2 - aabbH / 2

  let result = {
    x: Math.max(minX, Math.min(pos.x, maxX)),
    y: Math.max(minY, Math.min(pos.y, maxY)),
  }

  if (obstacles && obstacles.length > 0) {
    result = resolveObstacles(result, prevPos ?? null, unit, obstacles, baseDiamPx, boardWidthPx, boardHeightPx)
  }

  return result
}

function resolveObstacles(
  pos: { x: number; y: number },
  prevPos: { x: number; y: number } | null,
  unit: { cols: number; rows: number; rotation?: number },
  obstacles: Obstacle[],
  baseDiamPx: number,
  boardWidthPx: number,
  boardHeightPx: number,
): { x: number; y: number } {
  const aWpx = unit.cols * baseDiamPx + (unit.cols - 1) * CIRCLE_GAP_PX
  const aHpx = unit.rows * baseDiamPx
  const aW = (aWpx / boardWidthPx) * 100
  const aH = (aHpx / boardHeightPx) * 100
  let result = { ...pos }

  for (const obs of obstacles) {
    const bWpx = obs.unit.cols * baseDiamPx + (obs.unit.cols - 1) * CIRCLE_GAP_PX
    const bHpx = obs.unit.rows * baseDiamPx
    const bW = (bWpx / boardWidthPx) * 100
    const bH = (bHpx / boardHeightPx) * 100

    const aabb = getRotatedAABB(result, aW, aH, unit.rotation ?? 0)
    const babb = getRotatedAABB(obs.pos, bW, bH, obs.unit.rotation ?? 0)

    const overlapX = Math.min(aabb.x + aabb.w, babb.x + babb.w) - Math.max(aabb.x, babb.x)
    const overlapY = Math.min(aabb.y + aabb.h, babb.y + babb.h) - Math.max(aabb.y, babb.y)

    if (overlapX <= 0 || overlapY <= 0) continue

    if (prevPos) {
      const dx = result.x - prevPos.x
      const dy = result.y - prevPos.y
      if (Math.abs(dx) >= Math.abs(dy)) {
        const newAabbX = dx >= 0 ? babb.x - aabb.w : babb.x + babb.w
        result = { ...result, x: result.x + (newAabbX - aabb.x) }
      } else {
        const newAabbY = dy > 0 ? babb.y - aabb.h : babb.y + babb.h
        result = { ...result, y: result.y + (newAabbY - aabb.y) }
      }
    } else {
      if (overlapX < overlapY) {
        const centerA = aabb.x + aabb.w / 2
        const centerB = babb.x + babb.w / 2
        const newAabbX = centerA <= centerB ? babb.x - aabb.w : babb.x + babb.w
        result = { ...result, x: result.x + (newAabbX - aabb.x) }
      } else {
        const centerA = aabb.y + aabb.h / 2
        const centerB = babb.y + babb.h / 2
        const newAabbY = centerA <= centerB ? babb.y - aabb.h : babb.y + babb.h
        result = { ...result, y: result.y + (newAabbY - aabb.y) }
      }
    }
  }

  return result
}
```

- [ ] **Step 4: Run and confirm all tests pass**

```bash
npm test
```

Expected: all tests pass including existing obstacle tests.

- [ ] **Step 5: Commit**

```bash
git add src/utils/clamp.ts src/utils/clamp.test.ts
git commit -m "feat: use rotated AABB in clampPosition and obstacle resolution"
```

---

## Task 4: Server — save rotation and compute arc distance (TDD)

**Files:**
- Modify: `src/party/server.ts`
- Modify: `src/party/server.test.ts`

- [ ] **Step 1: Write failing tests**

Append to `src/party/server.test.ts`:

```typescript
describe('unit_moved — rotation', () => {
  function makeState() {
    let state = emptyState()
    state = applyEvent(state, { type: 'unit_added', name: 'Alpha', rows: 1, cols: 2, modelCount: 2 }, 'player-1')!
    const unitId = state.units[0].id
    // Place unit first
    state = applyEvent(state, { type: 'unit_moved', unitId, position: { x: 10, y: 10 } }, 'player-1')!
    return { state, unitId }
  }

  it('saves rotation on the unit when provided', () => {
    const { state, unitId } = makeState()
    const result = applyEvent(state, { type: 'unit_moved', unitId, position: { x: 20, y: 20 }, rotation: 45 }, 'player-1')!
    expect(result.units.find(u => u.id === unitId)!.rotation).toBe(45)
  })

  it('defaults rotation to 0 when not provided (backward compat)', () => {
    const { state, unitId } = makeState()
    const result = applyEvent(state, { type: 'unit_moved', unitId, position: { x: 20, y: 20 } }, 'player-1')!
    expect(result.units.find(u => u.id === unitId)!.rotation).toBe(0)
  })

  it('stores fromRotation and toRotation on the log entry', () => {
    const { state, unitId } = makeState()
    // state unit currently has rotation 0 (default)
    const result = applyEvent(state, { type: 'unit_moved', unitId, position: { x: 20, y: 20 }, rotation: 90 }, 'player-1')!
    const entry = result.moveLog.at(-1)!
    expect(entry.fromRotation).toBe(0)
    expect(entry.toRotation).toBe(90)
  })

  it('adds arc distance to distanceInches when unit rotates in place', () => {
    const { state, unitId } = makeState()
    // 2×1 unit, rotate 360°, diam = baseDiamPx / (boardWidthPx / 44) inches
    // baseDiamPx=20, boardWidthPx=400 → diamInches = 20 / (400/44) = 2.2"
    // maxRadius = 0.5 × 2.2 = 1.1"
    // arc = 1.1 × 2π ≈ 6.912"
    // straight-line move = 0 (same position)
    const result = applyEvent(state, {
      type: 'unit_moved',
      unitId,
      position: { x: 10, y: 10 },  // same position
      rotation: 360,
      baseDiamPx: 20,
      boardWidthPx: 400,
    }, 'player-1')!
    const entry = result.moveLog.at(-1)!
    const diamInches = 20 / (400 / 44)
    const expectedArc = 0.5 * diamInches * 2 * Math.PI
    expect(entry.distanceInches).toBeCloseTo(expectedArc, 1)
  })

  it('distanceInches is unchanged when no rotation is provided', () => {
    const { state, unitId } = makeState()
    const result = applyEvent(state, { type: 'unit_moved', unitId, position: { x: 10, y: 10 } }, 'player-1')!
    expect(result.moveLog.at(-1)!.distanceInches).toBe(0)
  })
})
```

- [ ] **Step 2: Run and confirm failure**

```bash
npm test
```

Expected: new rotation tests fail (rotation not saved, arc not computed).

- [ ] **Step 3: Update the `ClientMsg` type and `unit_moved` handler in `src/party/server.ts`**

Change the `ClientMsg` type:

```typescript
type ClientMsg =
  | { type: 'unit_added'; name: string; rows: number; cols: number; modelCount: number }
  | { type: 'unit_moved'; unitId: string; position: { x: number; y: number }; rotation?: number; baseDiamPx?: number; boardWidthPx?: number }
  | { type: 'unit_deleted'; unitId: string }
  | { type: 'unit_undo' }
  | { type: 'unit_redo' }
```

Add `rotation: 0` to the `unit_added` branch where the `Unit` object is constructed:

```typescript
const unit: Unit = {
  id: crypto.randomUUID(),
  name: msg.name,
  color: COLORS[colorIdx % COLORS.length],
  rows: msg.rows,
  cols: msg.cols,
  modelCount: msg.modelCount,
  position: null,
  rotation: 0,
  ownerId: playerId,
}
```

Replace the `unit_moved` branch with:

```typescript
if (msg.type === 'unit_moved') {
  const unit = state.units.find(u => u.id === msg.unitId)
  if (!unit || unit.ownerId !== playerId) return null

  const fromPosition = unit.position
  const fromRotation = unit.rotation ?? 0
  const toRotation = msg.rotation ?? 0
  const prunedLog = state.moveLog.filter(e => e.playerId !== playerId || e.active)

  const straightInches = fromPosition ? calcDistanceInches(fromPosition, msg.position) : 0

  let arcInches = 0
  if (msg.baseDiamPx && msg.boardWidthPx && msg.baseDiamPx > 0 && msg.boardWidthPx > 0) {
    const diamInches = msg.baseDiamPx / (msg.boardWidthPx / BOARD_WIDTH_INCHES)
    arcInches = calcRotationArcInches(unit, toRotation - fromRotation, diamInches)
  }

  const logEntry: MoveLogEntry = {
    id: crypto.randomUUID(),
    unitId: unit.id,
    unitName: unit.name,
    unitColor: unit.color,
    playerId,
    fromPosition,
    toPosition: msg.position,
    fromRotation,
    toRotation,
    distanceInches: fromPosition ? straightInches + arcInches : 0,
    timestamp: Date.now(),
    active: true,
  }
  const event: GameEvent = {
    id: crypto.randomUUID(),
    type: 'unit_moved',
    playerId,
    timestamp: Date.now(),
    payload: { unitId: msg.unitId, position: msg.position, rotation: toRotation },
  }
  return {
    ...state,
    units: state.units.map(u =>
      u.id === msg.unitId ? { ...u, position: msg.position, rotation: toRotation } : u,
    ),
    events: [...state.events, event],
    moveLog: [...prunedLog, logEntry],
  }
}
```

**Replace** the existing `import { calcDistanceInches } from '../utils/board'` line at the top of `server.ts` with:

```typescript
import { calcDistanceInches, calcRotationArcInches, BOARD_WIDTH_INCHES } from '../utils/board'
```

`BOARD_WIDTH_INCHES` is already exported from `board.ts` (line 1). `calcRotationArcInches` was added in Task 2.

- [ ] **Step 4: Run and confirm pass**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/party/server.ts src/party/server.test.ts
git commit -m "feat: save rotation on unit and add arc distance to move log"
```

---

## Task 5: Server — undo/redo restores rotation (TDD)

**Files:**
- Modify: `src/party/server.ts`
- Modify: `src/party/server.test.ts`

- [ ] **Step 1: Write failing tests**

Append to `src/party/server.test.ts`:

```typescript
describe('unit_undo / unit_redo — rotation', () => {
  function makeRotatedState() {
    let state = emptyState()
    state = applyEvent(state, { type: 'unit_added', name: 'Alpha', rows: 1, cols: 1, modelCount: 1 }, 'player-1')!
    const unitId = state.units[0].id
    // Place at rotation 0
    state = applyEvent(state, { type: 'unit_moved', unitId, position: { x: 10, y: 10 }, rotation: 0 }, 'player-1')!
    // Move + rotate to 90°
    state = applyEvent(state, { type: 'unit_moved', unitId, position: { x: 50, y: 50 }, rotation: 90 }, 'player-1')!
    return { state, unitId }
  }

  it('undo restores fromRotation on the unit', () => {
    const { state, unitId } = makeRotatedState()
    const result = applyEvent(state, { type: 'unit_undo' }, 'player-1')!
    expect(result.units.find(u => u.id === unitId)!.rotation).toBe(0)
  })

  it('redo restores toRotation on the unit', () => {
    const { state, unitId } = makeRotatedState()
    let result = applyEvent(state, { type: 'unit_undo' }, 'player-1')!
    result = applyEvent(result, { type: 'unit_redo' }, 'player-1')!
    expect(result.units.find(u => u.id === unitId)!.rotation).toBe(90)
  })
})
```

- [ ] **Step 2: Run and confirm failure**

```bash
npm test
```

Expected: undo/redo rotation tests fail.

- [ ] **Step 3: Update undo and redo branches in `src/party/server.ts`**

In the `unit_undo` branch, change the `units` map to also restore `fromRotation`:

```typescript
if (msg.type === 'unit_undo') {
  let lastActiveIdx = -1
  for (let i = state.moveLog.length - 1; i >= 0; i--) {
    if (state.moveLog[i].playerId === playerId && state.moveLog[i].active) {
      lastActiveIdx = i
      break
    }
  }
  if (lastActiveIdx === -1) return null

  const entry = state.moveLog[lastActiveIdx]
  return {
    ...state,
    units: state.units.map(u =>
      u.id === entry.unitId
        ? { ...u, position: entry.fromPosition, rotation: entry.fromRotation }
        : u,
    ),
    moveLog: state.moveLog.map((e, i) => i === lastActiveIdx ? { ...e, active: false } : e),
  }
}
```

In the `unit_redo` branch, change the `units` map to also restore `toRotation`:

```typescript
if (msg.type === 'unit_redo') {
  const firstInactiveIdx = state.moveLog.findIndex(e => e.playerId === playerId && !e.active)
  if (firstInactiveIdx === -1) return null

  const entry = state.moveLog[firstInactiveIdx]
  return {
    ...state,
    units: state.units.map(u =>
      u.id === entry.unitId
        ? { ...u, position: entry.toPosition, rotation: entry.toRotation }
        : u,
    ),
    moveLog: state.moveLog.map((e, i) => i === firstInactiveIdx ? { ...e, active: true } : e),
  }
}
```

- [ ] **Step 4: Run and confirm all tests pass**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/party/server.ts src/party/server.test.ts
git commit -m "feat: restore rotation on unit_undo and unit_redo"
```

---

## Task 6: Apply committed rotation to `DraggableToken` shadow

**Files:**
- Modify: `src/components/DraggableToken.tsx`

No unit tests — this is a visual rendering change. Verify manually in the browser.

- [ ] **Step 1: Apply `unit.rotation` to the shadow div in `src/components/DraggableToken.tsx`**

Replace the `transform` style line. The existing `CSS.Translate.toString(transform)` handles the drag offset. Append the rotation, filtering empty strings so they don't produce invalid CSS:

```typescript
import { useDraggable } from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import type { Unit } from '../types'
import UnitToken from './UnitToken'

type Props = {
  unit: Unit
  baseDiamPx: number
}

export default function DraggableToken({ unit, baseDiamPx }: Props) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: unit.id,
    data: { type: 'placed' },
  })

  const translateStr = CSS.Translate.toString(transform)
  const rotateStr = `rotate(${unit.rotation ?? 0}deg)`
  const transformStr = [translateStr, rotateStr].filter(Boolean).join(' ')

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      style={{
        position: 'absolute',
        left: `${unit.position!.x}%`,
        top: `${unit.position!.y}%`,
        transform: transformStr,
        opacity: isDragging ? 0.3 : 1,
        cursor: 'grab',
        touchAction: 'none',
      }}
    >
      <UnitToken unit={unit} baseDiamPx={baseDiamPx} />
    </div>
  )
}
```

- [ ] **Step 2: Compile check**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add src/components/DraggableToken.tsx
git commit -m "feat: apply committed rotation to DraggableToken shadow"
```

---

## Task 7: App.tsx — draft rotation state, wheel listener, ghost and DragOverlay

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Add `draftRotation` state and ref after the existing `ghost` state**

In `src/App.tsx`, add these two lines after `const [ghost, setGhost] = useState(...)`:

```typescript
const [draftRotation, setDraftRotation] = useState<number | null>(null)
const draftRotationRef = useRef<number | null>(null)
```

`useRef` is already imported at the top of the file.

- [ ] **Step 2: Update `handleDragStart` to initialise draft rotation**

```typescript
function handleDragStart(event: DragStartEvent) {
  const unit = units.find(u => u.id === event.active.id) ?? null
  setActiveUnit(unit)
  setIsTrashOver(false)
  setGhost(null)
  const initial = unit?.rotation ?? 0
  setDraftRotation(initial)
  draftRotationRef.current = initial
}
```

- [ ] **Step 3: Add the document wheel listener effect**

Add this `useEffect` after the existing `useEffect(() => { unitsRef.current = units }, [units])`:

```typescript
const DEGREES_PER_PIXEL = 0.05  // ~5° per 100-unit scroll notch

useEffect(() => {
  if (!activeUnit) return
  function handleWheel(e: WheelEvent) {
    e.preventDefault()
    const next = (draftRotationRef.current ?? 0) + e.deltaY * DEGREES_PER_PIXEL
    draftRotationRef.current = next
    setDraftRotation(next)
  }
  document.addEventListener('wheel', handleWheel, { passive: false })
  return () => document.removeEventListener('wheel', handleWheel)
}, [activeUnit])
```

- [ ] **Step 4: Update the ghost state type and `handleDragMove`**

The `ghost` state currently has type `{ unit: Unit; position: { x: number; y: number } } | null`. Change the `useState` initialiser to the new shape:

```typescript
const [ghost, setGhost] = useState<{ unit: Unit; position: { x: number; y: number }; rotation: number } | null>(null)
```

In `handleDragMove`, pass `rotation` for both the ghost and the `clampPosition` call. The full updated function:

```typescript
function handleDragMove(event: DragMoveEvent) {
  if (event.over?.id !== 'board') {
    setGhost(null)
    return
  }

  const unit = units.find(u => u.id === event.active.id)
  if (!unit) { setGhost(null); return }

  const board = boardRef.current
  if (!board) { setGhost(null); return }

  const boardW = boardSizeRef.current.w || board.offsetWidth
  const boardH = boardSizeRef.current.h || board.offsetHeight
  const diam = baseDiamPx || (boardW / 1120) * 32
  const rotation = draftRotationRef.current ?? (unit.rotation ?? 0)

  let desiredPct: { x: number; y: number }
  if (unit.position !== null) {
    desiredPct = {
      x: unit.position.x + (event.delta.x / boardW) * 100,
      y: unit.position.y + (event.delta.y / boardH) * 100,
    }
  } else {
    const boardRect = board.getBoundingClientRect()
    const activeRect = (event.active.rect.current as { translated: DOMRect | null }).translated
    if (!activeRect) { setGhost(null); return }
    desiredPct = {
      x: ((activeRect.left - boardRect.left) / boardW) * 100,
      y: ((activeRect.top  - boardRect.top)  / boardH) * 100,
    }
  }

  const othersPct = units
    .filter(u => u.position !== null && u.id !== unit.id)
    .map(u => ({ pos: u.position!, unit: { cols: u.cols, rows: u.rows, rotation: u.rotation ?? 0 } }))

  const finalPct = clampPosition(
    desiredPct,
    { ...unit, rotation },
    diam, boardW, boardH,
    unit.position,
    othersPct,
  )

  // Compare finalPct (board + obstacle clamped) against board-only clamped to
  // detect whether an obstacle is causing a meaningful push (> 0.5px). Using
  // clampPosition with no obstacles gives the correct rotated-AABB board clamp.
  const boardOnlyPos = clampPosition(desiredPct, { ...unit, rotation }, diam, boardW, boardH, unit.position)
  const dxPx = (finalPct.x - boardOnlyPos.x) * boardW / 100
  const dyPx = (finalPct.y - boardOnlyPos.y) * boardH / 100
  if (Math.hypot(dxPx, dyPx) > 0.5) {
    setGhost({ unit, position: finalPct, rotation })
  } else {
    setGhost(null)
  }
}
```

- [ ] **Step 5: Update `handleDragEnd` to send rotation**

```typescript
function handleDragEnd(event: DragEndEvent) {
  const rotation = draftRotationRef.current ?? 0
  setActiveUnit(null)
  setIsTrashOver(false)
  setGhost(null)
  setDraftRotation(null)
  draftRotationRef.current = null

  const { active, over, delta } = event
  if (!over) return

  const unit = unitsRef.current.find(u => u.id === active.id)
  if (!unit || unit.ownerId !== localPlayerId) return

  const board = boardRef.current
  if (!board) return

  const boardW = board.offsetWidth
  const boardH = board.offsetHeight
  const diam = baseDiamPx || (boardW / 1120) * 32
  setBaseDiamPx((boardW / 1120) * 32)

  if (over.id === 'trashcan' && unit.position !== null) {
    send({ type: 'unit_deleted', unitId: unit.id })
    return
  }

  if (over.id === 'board') {
    let rawPct: { x: number; y: number }

    if (unit.position === null) {
      const boardRect = board.getBoundingClientRect()
      const activeRect = (active.rect.current as { translated: DOMRect | null }).translated
      if (!activeRect) return
      rawPct = {
        x: ((activeRect.left - boardRect.left) / boardW) * 100,
        y: ((activeRect.top  - boardRect.top)  / boardH) * 100,
      }
    } else {
      rawPct = {
        x: unit.position.x + (delta.x / boardW) * 100,
        y: unit.position.y + (delta.y / boardH) * 100,
      }
    }

    const othersPct = unitsRef.current
      .filter(u => u.position !== null && u.id !== unit.id)
      .map(u => ({ pos: u.position!, unit: { cols: u.cols, rows: u.rows, rotation: u.rotation ?? 0 } }))

    const pos = clampPosition(
      rawPct,
      { ...unit, rotation },
      diam, boardW, boardH,
      unit.position,
      othersPct,
    )

    send({ type: 'unit_moved', unitId: unit.id, position: pos, rotation, baseDiamPx: diam, boardWidthPx: boardW })
  }
}
```

- [ ] **Step 6: Wrap DragOverlay content with rotation**

Replace the `<DragOverlay>` JSX:

```tsx
<DragOverlay>
  {activeUnit && (
    <div style={{ transform: `rotate(${draftRotation ?? (activeUnit.rotation ?? 0)}deg)` }}>
      <UnitToken unit={activeUnit} baseDiamPx={baseDiamPx || 18} />
    </div>
  )}
</DragOverlay>
```

- [ ] **Step 7: Compile check and run tests**

```bash
npx tsc --noEmit && npm test
```

Expected: all tests pass, no type errors.

- [ ] **Step 8: Commit**

```bash
git add src/App.tsx
git commit -m "feat: add draftRotation state, wheel listener and rotation in dragEnd"
```

---

## Task 8: Board.tsx — apply rotation to ghost and opponent tokens

**Files:**
- Modify: `src/components/Board.tsx`

- [ ] **Step 1: Update the `Props` type and ghost rendering**

The `ghost` prop type must match the new ghost shape from App.tsx. Also apply rotation to opponent tokens. Full updated file:

```typescript
import { forwardRef, useState, useEffect } from 'react'
import { useDroppable } from '@dnd-kit/core'
import './Board.css'
import type { Unit } from '../types'
import DraggableToken from './DraggableToken'
import UnitToken from './UnitToken'

type Props = {
  units: Unit[]
  baseDiamPx: number
  mapUrl: string | null
  ghost?: { unit: Unit; position: { x: number; y: number }; rotation: number } | null
  localPlayerId: string
}

const Board = forwardRef<HTMLDivElement, Props>(function Board(
  { units, baseDiamPx, mapUrl, ghost, localPlayerId },
  ref,
) {
  const { setNodeRef } = useDroppable({ id: 'board' })
  const placed = units.filter(u => u.position !== null)
  const [mapIsLandscape, setMapIsLandscape] = useState(false)

  useEffect(() => { setMapIsLandscape(false) }, [mapUrl])

  return (
    <div className="board-wrapper">
      <div
        className="board"
        ref={(el) => {
          setNodeRef(el)
          if (typeof ref === 'function') ref(el)
          else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = el
        }}
      >
        {mapUrl && (
          <img
            src={mapUrl}
            alt=""
            className={`board-map${mapIsLandscape ? ' board-map--landscape' : ''}`}
            onLoad={e => setMapIsLandscape(e.currentTarget.naturalWidth > e.currentTarget.naturalHeight)}
          />
        )}
        {placed.map(unit =>
          unit.ownerId === localPlayerId ? (
            <DraggableToken key={unit.id} unit={unit} baseDiamPx={baseDiamPx} />
          ) : (
            <div
              key={unit.id}
              style={{
                position: 'absolute',
                left: `${unit.position!.x}%`,
                top: `${unit.position!.y}%`,
                transform: `rotate(${unit.rotation ?? 0}deg)`,
              }}
            >
              <UnitToken unit={unit} baseDiamPx={baseDiamPx} />
            </div>
          ),
        )}
        {ghost && (
          <div
            className="board-ghost"
            style={{
              left: `${ghost.position.x}%`,
              top: `${ghost.position.y}%`,
              transform: `rotate(${ghost.rotation}deg)`,
            }}
          >
            <UnitToken unit={ghost.unit} baseDiamPx={baseDiamPx} />
          </div>
        )}
      </div>
    </div>
  )
})

export default Board
```

- [ ] **Step 2: Compile check and run tests**

```bash
npx tsc --noEmit && npm test
```

Expected: no errors, all tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/components/Board.tsx
git commit -m "feat: apply rotation to ghost and opponent tokens in Board"
```

---

## Self-Review Checklist

After completing all tasks, verify against the spec:

- [ ] `Unit.rotation` persists on server and defaults to 0 for old units (`unit.rotation ?? 0` in server)
- [ ] Wheel scroll during drag updates `draftRotation` smoothly (~5°/notch) and prevents page scroll
- [ ] Ghost shows draft rotation; DragOverlay shows draft rotation; shadow shows committed rotation
- [ ] Board-edge clamping uses rotated AABB (3×1 unit at 90° has narrower x footprint)
- [ ] Obstacle collision uses rotated AABB for both dragged unit and obstacles
- [ ] Move log `distanceInches` = straight-line + arc of furthest model
- [ ] Undo restores `fromRotation`; redo restores `toRotation`
- [ ] All existing tests still pass (`npm test`)
- [ ] TypeScript compiles with no errors (`npx tsc --noEmit`)
