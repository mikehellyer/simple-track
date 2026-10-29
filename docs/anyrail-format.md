# AnyRail 7 — format notes

Findings from AnyRail 7.23.0 (`~/Projects/AnyRail7_Original_Install/`) and two sample
layouts (`Dunnaemare.any`, `Hornby Dublo.any`). Simple-Track is a clean-room program; these
notes exist so it can **import** layouts. Nothing from AnyRail's binaries is reused.

## Installer

`AnyRail7.23.0.msi` (Advanced Installer) → stream `disk1.cab` (LZX) → 19 files:

| File | What it is |
|---|---|
| `AnyRail5.exe` | x64 C++: MFC + Codejock Xtreme Toolkit UI, Urho3D 3D view, Assimp. Protected with Oreans Code Virtualizer (`.vlizer` section). Track libraries live inside it, not readable. |
| `Data.pak`, `CoreData.pak` | Urho3D packages: 3D track models (`3DObjects/<lib>/<part>.mdl`), shaders, textures. No track geometry. |
| `ARTexts*.txt` | UI translations (`KEY "text"` lines, UTF-8 BOM). |
| `ThumbNailProvider.dll`, `updater.exe`, `d3dcompiler_47.dll` | Explorer thumbnails, updater, D3D runtime. |

Urho3D package: `"ULZ4"`, u32 count, u32 checksum, then per entry `name\0, u32 offset,
u32 size, u32 checksum`. Each file is a run of LZ4 blocks, each with a **u16** unpacked
size + **u16** packed size header. Tools: `research/pak_list.py`, `research/pak_get.py`.

## `.any` layout files

A Boost.Serialization **binary archive**: header string `serialization::archive`,
library version 17, then `04 04 04 08` (sizes of int/long/float/double) and an
endianness int.

Boost conventions in use:

- Strings are `u64 length` + bytes (no terminator).
- Polymorphic objects start with an `i16 class_id`. On the first occurrence of a class, the
  class name follows as a string (`CPart`, `CTrackSegment`, `CSurface`, `CText`,
  `CWorkArea`), then `u8 tracking` and `u32 version` (e.g. `CPart` is version 0x53).
  After that comes a `u32 object_id`.
- **Class IDs are assigned in order of first appearance, so they differ between files**
  (`CPart` = 0x2e in Dunnaemare, 0x3f in Hornby Dublo). Look them up by name.
- Tracked objects that are referenced again (for example a connector shared by two joined
  pieces) are written only once. Later references are just `class_id + object_id`.

### What has been identified

- **Header:** `"AnyRail"`, settings and colours, then 7–8 font records
  (`"Arial Unicode MS"`, size double, colours).
- **Library list:** the library IDs used by the layout, as strings. Hornby Dublo also
  carries the full catalogue list (about 300 IDs such as `PC0100`, `00HDUBLO3`,
  `009H0eP`).
- **Layers:** a `"Layer 1"` name string. `CSurface` holds the background, with an embedded
  JPEG (4.6 MB in Hornby Dublo).
- **CPart:** zero padding, then the part number string (`SL-500`, `SL-E595`, `3701`…), the
  library ID string (`PC0100`), then the gauge (`"0-16.5"`, `"00"`).
- **Connector / endpoint objects:** `i16 class, u32 id, u32 id, double x, double y,
  double z, double heading (radians), string library`.
  - The heading points *into* the piece. Its direction vector is `(sin a, cos a)`.
  - A turnout has 3 connectors. On Peco SL-E595/E596 the diverging route is 12°.
- **CTrackSegment geometry**, two kinds seen so far:
  - **Cubic Bézier** (flex track): four point objects `(i16 class, u32 id, double x,
    double y)`. Control points are `P1 = P0 + L·dir(a0)` and `P2 = P3 + L·dir(a3)`.
  - **Arc** (sectional curves): six doubles, `x, y, angle, radius, sweep, length`.
    - `length` always equals `radius × |sweep|`. That is how arc records are found.
    - `(x, y)` is where the curve starts.
    - `angle` is the direction from the centre to the start point, measured with the
      y axis pointing up, and turned half a circle when `sweep` is negative. So the
      start's polar angle is `angle + (π if sweep < 0 else 0)`, and
      `centre = start − r·(cos, sin)` of that.
    - The curve runs on from there by `sweep`.
    - Checked on all 40 arcs in both samples: each either ends on a connector or, on a
      point, leads into the straight tail that does.
- **Units:** centimetres. Dunnaemare is a shelf layout of about 400 × 42 cm.
- **CText:** labels, for example `"Station Road - Hornby Dublo - 3 Rail"`.
- **CWorkArea:** near the end of the file, likely the baseboard outline.

`docs/images/dunnaemare-decoded.png` shows Dunnaemare redrawn from the file alone: flex
track in blue, turnouts in red (drawn connector-to-connector).

### The importer

`src/simple_track/core/anyrail.py` reads the records above by shape, with sanity checks,
rather than walking the archive class by class:

- **Parts:** a part number string immediately followed by a library ID string.
- **Connectors:** these must share the most common class ID, which filters out part
  headers that look like connectors. Both full records and back-references are
  collected.
- **Straights** are drawn between connectors that line up. **Straight lead-ins and
  tails on points** are bridged from the curve to the nearest connector.
- **Freehand curves:** a curve far from its part's connectors is track drawn freehand
  in AnyRail, with no part record of its own. It becomes a piece of its own.

### Still to do

- A schema-driven parser that walks every class by version, which would be more robust
  than matching record shapes.
- The straight-segment record layout, turnout routes, CWorkArea baseboard polygon, layers and
  colours, and text placement.
- More sample files would help, especially Peco Setrack OO and Peco N layouts, and a
  file with a single known piece at a known position.
