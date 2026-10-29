# Simple-Track

A model railway layout designer for Linux, macOS and Windows, in the spirit of AnyRail.
Plan layouts with Peco and Hornby sectional track in OO and N gauge, get a parts list, and
bring across layouts drawn in AnyRail.

## Track libraries

| Scale | Library | Pieces |
|---|---|---|
| OO | Hornby OO | 34 |
| OO | Peco Setrack (OO/HO, code 100) | 24 |
| OO | Peco Streamline (OO/HO, code 100) | 23 |
| OO | Peco Bullhead (OO, code 75) | 13 |
| N | Peco Setrack (N, code 80) | 21 |
| N | Peco Streamline (N, code 80) | 15 |
| N | Peco Finescale (N, code 55) | 19 |

The geometry comes from [XTrackCAD](https://sourceforge.net/projects/xtrkcad-fork/)'s
parameter files. `tools/xtp_to_library.py` converts them into Simple-Track's own JSON
(`src/simple_track/core/libraries/`). To add a library, add the `.xtp` file to `LIBRARIES`
in that script and re-run it.

## Using it

- **Add track:** pick a library on the left, then double-click a piece. It joins on at
  the **orange** end, and its far end becomes the new orange end, so you can keep
  double-clicking to build a run.
- **Tab** turns round the piece you just added. Use it to make a curve bend the other way
  or to put a point in backwards.
- **Click a red end** (a free connector) to build from there instead.
- **Drag** pieces to move them. When a free end comes close to another one, it snaps
  into place.
- **R** / **Shift+R** rotates the selection 15°, **Del** deletes it, and Ctrl-click
  selects more than one piece.
- **Wheel** zooms, **right- or middle-drag** pans, and **F** zooms to fit.
- **Undo/redo:** Ctrl+Z / Ctrl+Shift+Z.
- **File:** layouts save as `.strack` files (JSON). Open them from File ▸ Open.
- **AnyRail:** File ▸ Import AnyRail layout… (or open a `.any` directly).
  - Imported track keeps AnyRail's shapes and is drawn in grey. It can be moved,
    rotated and deleted, and new track can be joined onto it.
  - Background pictures, text labels and the baseboard outline aren't imported yet.

## Running from source

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt -e .
venv/bin/simple-track
```

Tests: `venv/bin/pytest`. The AnyRail tests use the sample layouts in
`~/Projects/AnyRail7_Original_Install/` when they're there (or wherever
`SIMPLE_TRACK_ANY_SAMPLES` points), and skip otherwise.

## Releases

Pushing a `v*` tag builds the Windows installer, the macOS `.dmg` and the Linux `.deb` on
GitHub Actions, then attaches them to a GitHub Release. The app checks that release feed
and offers updates; it never installs one without being asked.

## How the AnyRail import works

`docs/anyrail-format.md` has what has been worked out of AnyRail's file format.
`research/` holds the throwaway scripts used to work it out.

## Licence

Simple-Track is free software under the GNU General Public License, version 2 or (at your
option) any later version. See `LICENSE`. The track geometry is derived from XTrackCAD's
parameter files, which are under the same licence.
