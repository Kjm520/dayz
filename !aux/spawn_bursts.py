"""Correlate infected spawn bursts in an RPT with player positions in the ADM
and the infected zones around those positions.

usage: python -I spawn_bursts.py <RPT> <ADM> <zombie_territories.xml> [gap_seconds] [-v]

The RPT prints "PHYSICS : Initializing ragdoll NONE" once per creature the server
creates: infected, but also animals and players, so read a burst against the zones
listed under it (-v, which must follow the gap) before calling it infected. The CE
runs a spawn pass every ~57 s; bursts closer than gap_seconds (default 5) merge.
Use the dist/ zone file so dmin/dmax show the multiplied values the server runs.
"""
import math
import re
import sys
import xml.etree.ElementTree as ET

rpt_path, adm_path, zones_path = sys.argv[1:4]
GAP = float(sys.argv[4]) if len(sys.argv) > 4 else 5.0

RAG = re.compile(r"^\s*(\d+):(\d+):(\d+)\.(\d+)\s+PHYSICS\s+:\s+Initializing ragdoll")
ADM = re.compile(r'^(\d+):(\d+):(\d+) \| Player "([^"]+)" \(id=\w+ pos=<([-\d.]+), ([-\d.]+), ([-\d.]+)>\)(.*)$')
CONN = re.compile(r'^(\d+):(\d+):(\d+) \| Player "([^"]+)" \(id=\w+\) is connecting')


def monotonic(times):
    """Add 24 h whenever the clock wraps past midnight."""
    out, offset, last = [], 0.0, None
    for t in times:
        if last is not None and t + offset < last - 3600:
            offset += 86400
        v = t + offset
        out.append(v)
        last = v
    return out


def hms(sec):
    sec %= 86400
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


# --- RPT: ragdoll init lines -> bursts
raw = []
with open(rpt_path, encoding="utf-8", errors="replace") as f:
    for line in f:
        m = RAG.match(line)
        if m:
            h, mi, s, ms = (int(x) for x in m.groups())
            raw.append(h * 3600 + mi * 60 + s + ms / 1000.0)
times = monotonic(raw)
bursts = []
for t in times:
    if bursts and t - bursts[-1][-1] <= GAP:
        bursts[-1].append(t)
    else:
        bursts.append([t])

# --- ADM: positions and session edges
adm_raw = []
with open(adm_path, encoding="utf-8", errors="replace") as f:
    for line in f:
        m = ADM.match(line)
        if m:
            h, mi, s = (int(x) for x in m.groups()[:3])
            x, z = float(m.group(5)), float(m.group(6))
            adm_raw.append((h * 3600 + mi * 60 + s, x, z, m.group(4), m.group(8).strip()))
            continue
        m = CONN.match(line)
        if m:
            h, mi, s = (int(x) for x in m.groups()[:3])
            adm_raw.append((h * 3600 + mi * 60 + s, None, None, m.group(4), "is connecting"))
adm_t = monotonic([a[0] for a in adm_raw])
adm = [(t,) + a[1:] for t, a in zip(adm_t, adm_raw)]
positions = [a for a in adm if a[1] is not None]

# --- zones
zones = []
for z in ET.parse(zones_path).getroot().iter("zone"):
    zones.append((z.get("name"), float(z.get("x")), float(z.get("z")), float(z.get("r")),
                  int(z.get("dmin")), int(z.get("dmax"))))


def nearest_pos(t, name):
    best = None
    for p in positions:
        if p[3] != name:
            continue
        d = abs(p[0] - t)
        if best is None or d < best[0]:
            best = (d, p)
    return best


names = sorted({p[3] for p in positions})


def zones_near(x, z, limit):
    out = []
    for name, zx, zz, r, dmin, dmax in zones:
        d = math.hypot(zx - x, zz - z)
        if d - r <= limit:  # edge of the zone within `limit` of the player
            out.append((d, name, dmin, dmax, r))
    return sorted(out)


VERBOSE = "-v" in sys.argv

print("session edges (ADM):")
for a in adm:
    if "connect" in a[4]:
        print("  %s  %-14s %s" % (hms(a[0]), a[3], a[4]))
print()
print("players with positions:", ", ".join(names))
print("ragdoll-init bursts (gap > %.0fs): %d bursts, %d lines total" % (GAP, len(bursts), len(times)))
print()
for b in bursts:
    t0, t1, n = b[0], b[-1], len(b)
    line = "%s  n=%3d" % (hms(t0), n)
    found = False
    for name in names:
        np_ = nearest_pos(t0, name)
        if np_ is None or np_[0] > 900:
            continue
        found = True
        dt, p = np_
        line += "   %s@%s(%+4ds) <%.0f, %.0f>" % (name[:8], hms(p[0]), p[0] - t0, p[1], p[2])
    print(line if found else line + "  (no player position within 15 min)")
    if not VERBOSE:
        continue
    for name in names:
        np_ = nearest_pos(t0, name)
        if np_ is None or np_[0] > 900:
            continue
        p = np_[1]
        for d, zname, dmin, dmax, r in zones_near(p[1], p[2], 400):
            tag = "awake@300" if d - r <= 300 else "300-400  "
            print("        %-8s %s  %-22s dmin=%-3d dmax=%-3d r=%-4.0f centre %4.0f m" % (name[:8], tag, zname, dmin, dmax, r, d))
