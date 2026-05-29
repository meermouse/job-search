# Build Versioning System — Design

**Date:** 2026-05-29  
**Project:** tabletop-kit  
**Status:** Approved

---

## Overview

Automatic build versioning using a `X.X.X.X` format. The first two numbers (major, minor) are bumped manually by editing a file. The last two (patch, build) are auto-incremented by CI on every push to master.

---

## Version Format

```
major.minor.patch.build
```

| Segment | Who increments | When |
|---------|---------------|------|
| major   | Developer (manual) | Public releases |
| minor   | Developer (manual) | Big patches / feature milestones |
| patch   | CI (auto) | Every merge from a branch into master |
| build   | CI (auto) | Every direct commit to master |

When patch increments, build resets to 0. When minor or major is manually bumped, the developer must also reset patch and build to 0 in the same commit.

---

## Storage — `version.json`

A file at the repo root:

```json
{ "major": 0, "minor": 1, "patch": 0, "build": 0 }
```

This is the single source of truth. It is committed to git, so the current version is always visible in the repo. Manual major/minor bumps are done by editing this file and committing.

---

## CI Workflow — `version-bump` job

Added to `.github/workflows/ci.yml`. Runs only on `push` to master (not on PRs), after the `build` job passes.

**Steps:**

1. Checkout the repo
2. Read `version.json` using `jq`
3. Detect commit type by counting git parents:
   - `git log -1 --format="%P" HEAD | wc -w` returns 1 for a direct commit, 2 for a merge commit
4. Compute new version:
   - Direct commit → `build + 1`, all other segments unchanged
   - Merge commit → `patch + 1`, `build` reset to `0`, major/minor unchanged
5. Write updated `version.json`
6. Commit as `chore: bump version to X.X.X.X [skip ci]`
7. Push to master

The `[skip ci]` suffix prevents GitHub Actions from re-triggering on the bump commit. Netlify is unaffected by `[skip ci]` and will deploy as normal.

**Permissions required:** `contents: write` on the `version-bump` job.

**Git identity for the auto-commit:**
```
user.name  = github-actions[bot]
user.email = github-actions[bot]@users.noreply.github.com
```

---

## App Integration

### TypeScript config

`tsconfig.app.json` needs `"resolveJsonModule": true` added to `compilerOptions` so TypeScript resolves the JSON import.

### Import

`version.json` is imported directly in `Board.tsx`:

```typescript
import version from '../../version.json'
const versionString = `${version.major}.${version.minor}.${version.patch}.${version.build}`
```

### Display

A small overlay rendered inside the `.board` div in `Board.tsx`:

```tsx
<div className="board-version">v{versionString}</div>
```

CSS — absolutely positioned bottom-right, muted, non-interactive:

```css
.board-version {
  position: absolute;
  bottom: 6px;
  right: 8px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.35);
  pointer-events: none;
  user-select: none;
}
```

---

## Files Changed

| File | Change |
|------|--------|
| `version.json` | New file — initial value `{ "major": 0, "minor": 1, "patch": 0, "build": 0 }` |
| `.github/workflows/ci.yml` | Add `version-bump` job |
| `tsconfig.app.json` | Add `"resolveJsonModule": true` |
| `src/components/Board.tsx` | Import version.json, render `.board-version` overlay |
| `src/components/Board.css` | Add `.board-version` styles |

---

## Edge Cases

- **Manual major/minor bump:** Developer edits `version.json`, resets patch and build to 0 in the same commit. CI then increments build by 1 on that commit (making it e.g. `1.0.0.1`). This is correct — the reset commit itself counts as a direct commit.
- **Simultaneous pushes:** If two pushes land in quick succession, the second `version-bump` push may fail due to a non-fast-forward conflict. This is an acceptable race condition for a solo/two-player project; the second bump will simply not occur. A retry or rebase strategy is not warranted at this scale.
- **`workflow_dispatch`:** Manual workflow triggers do not run `version-bump` (the job condition is `github.event_name == 'push'`), so manually re-running CI does not increment the version.
