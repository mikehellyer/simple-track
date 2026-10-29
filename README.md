# Simple-Track

A model railway layout designer for Linux, macOS and Windows. Plan layouts with Peco and
Hornby sectional track in OO and N gauge, and get a parts list of everything used.

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

- **Drag track in:** drag a piece from the library onto the layout.
  - Over empty board, it goes down where you drop it.
  - Bring one of its ends near a free end, or drop it right on a free end, and it
    turns and snaps on. A **green** ring shows the end it will join.
- **Add track by double-clicking:** double-click a piece and it joins on at the
  **orange** end. Its far end becomes the new orange end, so you can keep
  double-clicking to build a run.
- **Tab** turns round the piece you just added. Use it to make a curve bend the other way
  or to put a point in backwards.
- **Click a red end** (a free connector) to build from there instead.
- **Drag** pieces already on the layout to move them. When a free end comes close to
  another one (up to 45° out of line), a green ring shows where it will join, and it
  snaps on when you let go.
- **R** / **Shift+R** rotates the selection 15°, **Del** deletes it, and Ctrl-click
  selects more than one piece.
- **Wheel** zooms, **right- or middle-drag** pans, and **F** zooms to fit.
- **Undo/redo:** Ctrl+Z / Ctrl+Shift+Z.
- **File:** layouts save as `.strack` files (JSON). Open them from File ▸ Open.

## Running from source

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt -e .
venv/bin/simple-track
```

Tests: `venv/bin/pytest`. A few tests need sample layout files that aren't kept in the
repo; they skip when those aren't on the machine.

## Releases

Pushing a `v*` tag builds the Windows installer, the macOS `.dmg` and the Linux `.deb` on
GitHub Actions, then attaches them to a GitHub Release. The app checks that release feed
and offers updates; it never installs one without being asked.

## Licence

Simple-Track is free software under the GNU General Public License, version 2 or (at your
option) any later version. See `LICENSE`. The track geometry is derived from XTrackCAD's
parameter files, which are under the same licence.
