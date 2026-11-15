#!/usr/bin/env python3
"""
calimoto2mia — rewrite a Calimoto GPX export so the Aprilia MIA app accepts it.

Why it's needed
---------------
Calimoto exports planned rides as GPX <rte>/<rtept> (route points) with bare,
unnamed <wpt> via-points, no elevation and no track. The Aprilia MIA app's
route import consumes Kurviger-style files: metadata + named waypoints
(<wpt> with <name>/<sym>/<type>) + a <trk>/<trkseg>/<trkpt> line. The known
workaround (import into Kurviger, export again) just rewrites the file into
that shape; this tool does the same rewrite locally, no account needed.

Usage
-----
    python3 calimoto2mia.py "Tour vom 2026-11-14.gpx"
    python3 calimoto2mia.py tour.gpx out.gpx
    python3 calimoto2mia.py tour.gpx --ele          # fetch real elevation online
"""

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

NS = "http://www.topografix.com/GPX/1/1"
NS10 = "http://www.topografix.com/GPX/1/0"
XSI = "http://www.w3.org/2001/XMLSchema-instance"


def q(tag, ns=NS):
    return f"{{{ns}}}{tag}"


def local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def detect_ns(root):
    return NS10 if root.tag == q("gpx", NS10) else NS


def text(el):
    return (el.text or "").strip() if el is not None else ""


def fmt_latlon(v):
    s = f"{float(v):.6f}"
    return s


def iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_elevations(points):
    """Batch-fetch elevations from Open-Meteo (public, keyless). Returns list
    of floats (same length as points); None entries where lookup failed."""
    eles = [None] * len(points)
    for start in range(0, len(points), 100):
        chunk = points[start:start + 100]
        url = ("https://api.open-meteo.com/v1/elevation?latitude="
               + ",".join(f"{p[0]:.6f}" for p in chunk)
               + "&longitude=" + ",".join(f"{p[1]:.6f}" for p in chunk))
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.load(resp)
            for i, e in enumerate(data.get("elevation", [])):
                if isinstance(e, (int, float)):
                    eles[start + i] = float(e)
        except Exception as exc:
            print(f"  elevation batch {start//100 + 1} failed: {exc}", file=sys.stderr)
    return eles


def convert(xml_bytes, elevations=None):
    root = ET.fromstring(xml_bytes)
    ns = detect_ns(root)

    # -- collect input -------------------------------------------------------
    meta = root.find(q("metadata", ns))
    if meta is None:
        meta = root.find(q("doc", ns))  # GPX 1.0 used <doc>
    name = text(meta.find(q("name", ns))) if meta is not None else ""
    desc = text(meta.find(q("desc", ns))) if meta is not None else ""

    routes = root.findall(q("rte", ns))
    waypoints = root.findall(q("wpt", ns))
    tracks = root.findall(q("trk", ns))

    # Route points become the track line. First route with points wins;
    # concatenate if several (Calimoto writes exactly one).
    line = []
    for rte in routes:
        for pt in rte.findall(q("rtept", ns)):
            line.append((float(pt.get("lat")), float(pt.get("lon")), pt))
    if not line:  # input already has a track — keep it as-is
        for trk in tracks:
            for seg in trk.findall(q("trkseg", ns)):
                for pt in seg.findall(q("trkpt", ns)):
                    line.append((float(pt.get("lat")), float(pt.get("lon")), pt))
    if not line:
        raise SystemExit("No route points or track points found — nothing to convert.")

    route_name = name or text(routes[0].find(q("name", ns))) if routes else name
    route_name = route_name or "Route"

    # -- elevation -----------------------------------------------------------
    if elevations is None:
        ele_values = [None] * len(line)
    else:
        ele_values = elevations

    # -- build Kurviger-style output ------------------------------------------
    ET.register_namespace("", NS)
    ET.register_namespace("xsi", XSI)
    out = ET.Element(q("gpx", NS))
    out.set("version", "1.1")
    out.set("creator", "calimoto2mia")
    out.set(f"{{{XSI}}}schemaLocation",
            f"{NS} http://www.topografix.com/GPX/1/1/gpx.xsd")

    metadata = ET.SubElement(out, q("metadata", NS))
    ET.SubElement(metadata, q("name", NS)).text = route_name
    if desc:
        ET.SubElement(metadata, q("desc", NS)).text = desc
    link = ET.SubElement(metadata, q("link", NS))
    link.set("href", "https://calimoto.com")
    ET.SubElement(link, q("text", NS)).text = "Converted from Calimoto export"
    ET.SubElement(metadata, q("time", NS)).text = iso_now()

    # Waypoints: original via-points, named and typed (Kurviger style)
    via_num = 0
    for wpt in waypoints:
        lat, lon = fmt_latlon(wpt.get("lat")), fmt_latlon(wpt.get("lon"))
        nw = ET.SubElement(out, q("wpt", NS))
        nw.set("lat", lat)
        nw.set("lon", lon)
        wname = text(wpt.find(q("name", NS)))
        if not wname:
            via_num += 1
            wname = f"Via {via_num}"
        ET.SubElement(nw, q("name", NS)).text = wname
        wdesc = text(wpt.find(q("desc", NS)))
        if wdesc:
            ET.SubElement(nw, q("desc", NS)).text = wdesc
        ET.SubElement(nw, q("sym", NS)).text = text(wpt.find(q("sym", NS))) or "Waypoint"
        wtype = text(wpt.find(q("type", NS)))
        ET.SubElement(nw, q("type", NS)).text = wtype or "via"

    # Start/finish markers at the line ends (Kurviger does this)
    s_lat, s_lon = line[0][0], line[0][1]
    e_lat, e_lon = line[-1][0], line[-1][1]
    sw = ET.SubElement(out, q("wpt", NS))
    sw.set("lat", fmt_latlon(s_lat))
    sw.set("lon", fmt_latlon(s_lon))
    ET.SubElement(sw, q("name", NS)).text = "Start"
    ET.SubElement(sw, q("sym", NS)).text = "Flag, Green"
    ET.SubElement(sw, q("type", NS)).text = "start"
    fw = ET.SubElement(out, q("wpt", NS))
    fw.set("lat", fmt_latlon(e_lat))
    fw.set("lon", fmt_latlon(e_lon))
    ET.SubElement(fw, q("name", NS)).text = "Finish"
    ET.SubElement(fw, q("sym", NS)).text = "Flag, Red"
    ET.SubElement(fw, q("type", NS)).text = "finish"

    # Track: the actual road line
    trk = ET.SubElement(out, q("trk", NS))
    ET.SubElement(trk, q("name", NS)).text = route_name
    seg = ET.SubElement(trk, q("trkseg", NS))
    for (lat, lon, src_pt), ele in zip(line, ele_values):
        tp = ET.SubElement(seg, q("trkpt", NS))
        tp.set("lat", fmt_latlon(lat))
        tp.set("lon", fmt_latlon(lon))
        src_ele = src_pt.find(q("ele", ns)) if src_pt is not None else None
        if ele is not None:
            ET.SubElement(tp, q("ele", NS)).text = f"{ele:.1f}"
        elif src_ele is not None and (src_ele.text or "").strip():
            ET.SubElement(tp, q("ele", NS)).text = src_ele.text.strip()

    xml = ET.tostring(out, encoding="UTF-8", xml_declaration=True)
    return xml.decode("utf-8"), route_name, len(line), via_num


def main():
    ap = argparse.ArgumentParser(description="Rewrite Calimoto GPX for the Aprilia MIA app.")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--ele", action="store_true",
                    help="fetch real elevations from open-elevation.com (needs internet)")
    args = ap.parse_args()

    with open(args.input, "rb") as f:
        data = f.read()

    elevations = None
    if args.ele:
        root = ET.fromstring(data)
        ns = detect_ns(root)
        pts = []
        for rte in root.findall(q("rte", ns)):
            for pt in rte.findall(q("rtept", ns)):
                pts.append((float(pt.get("lat")), float(pt.get("lon"))))
        if not pts:
            for trk in root.findall(q("trk", ns)):
                for seg in trk.findall(q("trkseg", ns)):
                    for pt in seg.findall(q("trkpt", ns)):
                        pts.append((float(pt.get("lat")), float(pt.get("lon"))))
        print(f"Fetching elevation for {len(pts)} points …", file=sys.stderr)
        elevations = fetch_elevations(pts)

    out, name, npts, nvia = convert(data, elevations)

    base = re.sub(r"\.gpx$", "", args.input, flags=re.I)
    output = args.output or f"{base}.mia.gpx"
    with open(output, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"OK  {output}  ({npts} track pts, {nvia} named via-points, route: {name})")


if __name__ == "__main__":
    main()
