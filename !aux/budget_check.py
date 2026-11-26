"""Does the ZombieMaxCount budget cap a solo player's awake cluster?

usage: python -I budget_check.py <zombie_territories.xml> <ZombieMaxCount> <wake_dist> [extra_scale]

The Scaling Spawner (RPT: "[n] Event :: dmax: S, P % == N pcs") gives each infected
event P = S / total_dmax of ZombieMaxCount pieces, S being the sum of dmax over the
event's zones. For every zone centre, this sums dmax over same-event zones whose edge
is within wake_dist of that centre (the cluster a player standing there wakes) and
reports the largest cluster per event against the event's budget. extra_scale
multiplies the file's dmin/dmax (e.g. 1.5 to preview 3x from a 2x dist file).
"""
import math
import re
import sys


def main():
    path, zmax, wake = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
    extra = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    text = open(path, encoding="utf-8").read()
    zones = []
    for tag in re.findall(r"<zone\b[^>]*/>", text):
        a = dict(re.findall(r'(\w+)="([^"]*)"', tag))
        zones.append((a["name"], float(a["x"]), float(a["z"]), float(a["r"]),
                      math.ceil(int(a["dmin"]) * extra), math.ceil(int(a["dmax"]) * extra)))
    by_event = {}
    for z in zones:
        by_event.setdefault(z[0], []).append(z)
    total = sum(z[5] for z in zones)
    print(f"zones {len(zones)}  total dmax {total}  ZombieMaxCount {zmax}  wake {wake:.0f} m  scale x{extra}")
    print(f"{'event':24} {'zones':>5} {'sum dmax':>8} {'budget':>6} | {'worst cluster':>13} {'dmin':>5} {'dmax':>5}  at")
    need = 0
    for name, zs in sorted(by_event.items(), key=lambda kv: -sum(z[5] for z in kv[1])):
        s = sum(z[5] for z in zs)
        if s == 0:
            continue
        share = s / total
        budget = max(10, round(share * zmax))  # RPT shows 10 pcs for 0 % events
        best = (0, 0, 0, None)
        for c in zs:
            awake = [z for z in zs if math.hypot(z[1] - c[1], z[2] - c[2]) - z[3] <= wake]
            dmax = sum(z[5] for z in awake)
            if dmax > best[0]:
                best = (dmax, sum(z[4] for z in awake), len(awake), c)
        need = max(need, math.ceil(best[0] / share))
        flag = f"  <-- CAPPED (needs ZombieMaxCount {math.ceil(best[0] / share)})" if best[0] > budget else ""
        c = best[3]
        print(f"{name:24} {len(zs):5} {s:8} {budget:6} | {best[2]:4} zones  {best[1]:5} {best[0]:5}  "
              f"<{c[1]:.0f}, {c[2]:.0f}>{flag}")
    print(f"\nZombieMaxCount at which no single cluster is budget-limited: {need}")


if __name__ == "__main__":
    main()
