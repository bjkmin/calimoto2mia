# cali2mia — Calimoto GPX → Aprilia MIA converter

Fixes Calimoto tour exports so the Aprilia MIA app accepts them, without the
Kurviger round-trip.

## Why Calimoto exports fail in MIA

A typical Calimoto tour export exposes three problems a strict importer (MIA)
trips on, while forgiving ones (Calimoto, Kurviger) silently tolerate them:

1. **GPX 1.0 namespace** (`http://www.topografix.com/GPX/1/0`, root element
   `<<gpx>>`, `<doc>` metadata). MIA expects GPX **1.1**.
2. **An empty `<rte>` with 408 route points but no `<name>`** anywhere —
   no route name, no start/finish, nothing displayable as a tour.
3. **4 anonymous via-point `<wpt>`s with no `<name>`/`<sym>`**, and **no
   `<ele>` elevation** anywhere.

Kurviger "works" because on import it normalizes all of this and on export
emits a clean GPX 1.1: a **named `<trk>` line** + **named waypoints**
(Start/Finish flags + via points). The converter reproduces exactly that shape.

## What the converter produces

- GPX 1.1 (`version="1.1"`, `creator="calimoto2mia"`, proper schemaLocation)
- `<metadata>` with the tour name (taken from the file name)
- Via-points (Calimoto allows up to 4) as named/typed `<wpt>`s (`Via 1..n`, `type=via`)
- `Start` (Flag, Green) and `Finish` (Flag, Red) `<wpt>`s at the line ends
- All route points as a `<trk><trkseg>` road line — coordinates identical to
  the input route (`kurviger-sample.gpx` shows the target shape)
- Optional real elevations via the keyless Open-Meteo elevation API
  (`--ele` / the checkbox; falls back gracefully when offline)

Validated against the official OGC GPX 1.1 schema: 0 errors.

## Android app (main tool)

**`calimoto2mia.html`** — a single self-contained file, runs fully offline in
any Android browser (Chrome/Firefox); nothing is uploaded anywhere.

Setup once:
1. Copy `calimoto2mia.html` to the phone (or host/open it from storage).
2. Open it in Chrome → three-dot menu → **Add to home screen**. Done — it's an
   app icon now.

Per tour:
1. In Calimoto: export the tour as GPX to a file (share → Save to file /
   Downloads).
2. Open the cali2mia icon, tap **Choose file**, pick the `.gpx`.
3. (Optional) tick *fetch real elevations* — needs internet.
4. Tap **Convert**, then **Download** → `…​.mia.gpx` lands in Downloads.
5. Import/open that file with the Aprilia MIA app, like any GPX route.

## Desktop script (same logic)

```
python3 calimoto2mia.py input.gpx [output.gpx] [--ele] [--name "Tour name"]
```

Standard-library only, Python 3.8+. Default output: `<input>.mia.gpx`.

## Files

| file | role |
|---|---|
| `calimoto2mia.html` | Android conversion tool (bookmark/add-to-home-screen) |
| `calimoto2mia.py` | desktop/reference converter |
| `kurviger-sample.gpx` | genuine Kurviger export — the target output shape to match |
| `gpx11.xsd` | OGC GPX 1.1 schema used for validation |

Tour `.gpx` files (Calimoto exports and converted output) are personal data and
gitignored; regenerate with the tool anytime. For more reference Kurviger
exports, fetch any route from kurviger.com (their CDN serves
`routes/tracks/<id>.gpx`).
