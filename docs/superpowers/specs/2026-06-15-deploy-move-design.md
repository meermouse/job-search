# Deploy Move Design

**Date:** 2026-06-15
**Feature:** Deploy move type — placing off-board units onto the board

---

## Overview

A "Deploy" move is undertaken when a player moves a unit from off-board to on-board. It auto-activates for all first placements (no context menu selection required), records in the move log as "Deploy" with no distance, supports rotation during the drag, and snaps units to the nearest zone boundary with an outward-facing rotation wherever the cursor is inside a zone.

---

## Move Type & Data Model

- Add `'Deploy'` to the `MoveType` union in `src/types.ts`.
- In `handleDragEnd` (App.tsx), detect first placement (all model positions null) and force `moveType = 'Deploy'` regardless of the currently selected move type.
- The server already sets `distanceInches: 0` for first placements — no server changes needed.
- Deploy entries in the move log show **no distance** ("Deploy", not "Deploy 0\"").
- Move log colour: teal `#2bb5a0` (distinct from Move grey, Charge gold, Pile In pink).
- No unit token badge for Deploy (it's a one-time placement, not an ongoing state).
- Translation key added: `moveLog.moveType.deploy` → `"Deploy"` in `src/locales/en.json`.
- Deploy is **not** added to the context menu — it is auto-detected only.

---

## Snap Computation

New utility: `src/utils/deploySnap.ts`

### Exported function

```ts
findDeploySnap(
  cursorPx: { x: number; y: number },
  zones: Zone[],
  boardW: number,
  boardH: number
): { snapPoint: { x: number; y: number }; outwardAngleDeg: number } | null
```

Returns `null` when the cursor is outside all zones (no snap, free placement).

### Algorithm

1. **Point-in-zone test** for each zone:
   - Rectangle: simple bounds check (all coords in board pixels, converted from normalised [0,1]).
   - Circle: `distance(cursor, centre) < r`.
   - Polygon: ray-casting algorithm.
2. If cursor is inside one or more zones, pick the zone whose boundary is **nearest** to the cursor.
3. Find the **nearest point on that zone's boundary**:
   - Rectangle / polygon: iterate edges, find nearest clamped point per edge, pick closest.
   - Circle: `centre + r * normalise(cursor − centre)`.
4. Compute **outward normal** at that boundary point (pointing away from zone interior):
   - Rectangle / polygon: perpendicular to the matching edge, pointing outward.
   - Circle: radial direction from centre through cursor.
5. Convert outward normal vector to the game's rotation angle convention (matching existing `rotation` fields on units).

---

## Rotation During Deploy Drag

The snap result feeds into the rotation system as a **base angle**; the scroll wheel accumulates an offset on top of it.

- `deploySnapRotationRef` holds the current outward angle from snap (updated each pointer-move while cursor is inside a zone).
- Existing scroll-wheel delta accumulates in `rotationOffsetRef`.
- **Applied rotation = `deploySnapRotationRef.current + rotationOffsetRef.current`.**
- When cursor leaves all zones (snap returns `null`): `deploySnapRotationRef` is set to the unit's original rotation so the scroll offset continues from there without a jump.
- On drag end, the final rotation is sent to the server as the unit's new rotation — same pipeline as today.
- The snap never mutates the stored rotation until drag ends.

---

## Visual Feedback

- Existing ghost and unit preview render as today.
- **Snap indicator**: a short dashed line extending from the unit's snap position in the outward-facing direction, styled consistently with existing snap rose lines / rotation arcs.
- Snap indicator is only visible while cursor is inside a zone (snap is active).
- No additional zone highlighting — existing coloured zone overlays are sufficient.

---

## Files Changed

| File | Change |
|------|--------|
| `src/types.ts` | Add `'Deploy'` to `MoveType` union |
| `src/App.tsx` | Force `moveType='Deploy'` on first placement; integrate `deploySnapRotationRef` into drag rotation logic; call `findDeploySnap` on pointer-move |
| `src/utils/deploySnap.ts` | **New file** — snap computation for all zone shapes |
| `src/components/Board.tsx` | Render snap indicator line during deploy drag |
| `src/components/MoveLog.tsx` | Add teal colour for Deploy; suppress distance display for Deploy entries |
| `src/locales/en.json` | Add `moveLog.moveType.deploy` |

No changes to: `src/party/server.ts`, `src/components/ContextMenu.tsx`, `src/components/DraggableToken.tsx`.
