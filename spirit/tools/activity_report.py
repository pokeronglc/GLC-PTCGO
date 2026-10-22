"""Player activity from the server log (no restart needed to run it).

    cd /opt/glc-ptcgo && venv/bin/python -m spirit.tools.activity_report --hours 48

The server keeps no history of the online count, so this estimates it:
  * players active  = distinct accounts that logged in, queued, challenged or
    played in the window (idle players sitting in menus are not counted);
  * games running   = games started minus games removed, at every moment;
  * players in game = 2 x human games (bot games count 1).
Shows the peaks, the busiest 15-minute windows and an hour-by-hour table.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import re
import subprocess
import sys

TS = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ - \w+ - (.*)$")
NAME_PATTERNS = (
    re.compile(r"User '([^']+)' successfully authenticated"),
    re.compile(r"\[Gameplay\] Player (\S+) "),
    re.compile(r"\[TCP\] \[[^\]]*\] Player '?([^' ]+)'? (?:requesting|accepting|challenging)"),
    re.compile(r"\[Matchmaking\] Player (\S+) (?:\(|entering|confirmed)"),
    re.compile(r"Initializing NetworkPlayer for (.+?)\.$"),
)
START = re.compile(r"\[Session ([0-9a-f-]{36})\] Starting GameSession")
BOT = re.compile(r"Starting bot match ([0-9a-f-]{36})")
END = re.compile(r"Removing session ([0-9a-f-]{36})")
WINDOW = dt.timedelta(minutes=15)


def read_log(hours):
    out = subprocess.run(
        ["journalctl", "-u", "glc", "--since", f"-{int(hours * 60)}min", "--no-pager"],
        capture_output=True, text=True, errors="replace").stdout
    for raw in out.splitlines():
        if "[TCP] Sent " in raw or "[TCP] Included " in raw:
            continue
        m = TS.search(raw)
        if m:
            yield dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), m.group(2)
        elif "systemd[" in raw and "Started" in raw:
            yield None, "RESTART"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=48)
    args = ap.parse_args(argv)

    seen = []                       # (time, name)
    bots = set()
    running = {}                    # game id -> players it counts
    games_peak = (0, None)
    players_peak = (0, None)
    last_t = None
    hourly_games = collections.defaultdict(int)
    for t, msg in read_log(args.hours):
        if t is None:               # restart: every game ends
            running.clear()
            continue
        last_t = t
        for pat in NAME_PATTERNS:
            m = pat.search(msg)
            if m and not m.group(1).startswith("Guest-AI"):
                seen.append((t, m.group(1)))
                break
        m = BOT.search(msg)
        if m:
            bots.add(m.group(1))
        m = START.search(msg)
        if m:
            running[m.group(1)] = 1 if m.group(1) in bots else 2
            hourly_games[t.strftime("%m-%d %H:00")] += 1
        m = END.search(msg)
        if m:
            running.pop(m.group(1), None)
        if len(running) > games_peak[0]:
            games_peak = (len(running), t)
        in_game = sum(running.values())
        if in_game > players_peak[0]:
            players_peak = (in_game, t)

    if not seen:
        print("No player activity found.")
        return 0

    everyone = {n for _, n in seen}
    by_hour = collections.defaultdict(set)
    for t, n in seen:
        by_hour[t.strftime("%m-%d %H:00")].add(n)

    # Busiest sliding 15-minute windows (distinct active players).
    best = []
    j = 0
    counts = collections.Counter()
    for i, (t, n) in enumerate(seen):
        counts[n] += 1
        while seen[j][0] < t - WINDOW:
            counts[seen[j][1]] -= 1
            if counts[seen[j][1]] == 0:
                del counts[seen[j][1]]
            j += 1
        best.append((len(counts), t))
    best.sort(reverse=True)
    shown, tops = [], []
    for n, t in best:
        if all(abs((t - s).total_seconds()) > 3600 for s in shown):
            shown.append(t)
            tops.append((n, t))
        if len(tops) == 5:
            break

    print(f"Activity in the last {args.hours:g} h (up to {last_t})\n")
    print(f"Different players seen:            {len(everyone)}")
    print(f"Peak players active in 15 minutes: {tops[0][0]}  (around {tops[0][1]:%m-%d %H:%M})")
    print(f"Peak games running at once:        {games_peak[0]}  (at {games_peak[1]})")
    print(f"Peak players in a game at once:    {players_peak[0]}  (at {players_peak[1]})")
    print("\nBusiest 15-minute windows (players active):")
    for n, t in tops:
        print(f"  {t:%m-%d %H:%M}  {n}")
    print("\nHour by hour (players active / games started):")
    peak_hour = max(len(v) for v in by_hour.values())
    for h in sorted(by_hour):
        n = len(by_hour[h])
        bar = "#" * round(30 * n / peak_hour)
        print(f"  {h}  {n:3} / {hourly_games.get(h, 0):3}  {bar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
