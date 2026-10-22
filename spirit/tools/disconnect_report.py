"""Mid-game disconnect report from the server log.

    cd /opt/glc-ptcgo && venv/bin/python -m spirit.tools.disconnect_report --hours 24

For every "Player X disconnected" inside a game it shows:
  * who, which game, the time;
  * WHY the socket closed, from the line just before it for that player's
    connection: client reset, client closed (EOF), our idle timeout, our send
    timeout (player's connection too slow to receive), newest-login kick, a
    server error, or a server restart;
  * what happened next: reconnected (and how long it took) or the 60 s grace
    ran out and the game was lost;
  * how long the server had been waiting on that player before the drop.
Then totals by reason, by player and by hour, plus server restarts and
errors in the window.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import re
import subprocess
import sys

TS = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ - (\w+) - (.*)$")
ADDR = r"\[TCP\] \[(\('[^']*', \d+\))\]"
GAME = r"\[Session ([0-9a-f-]{36})\]"


def read_log(hours: float):
    out = subprocess.run(
        ["journalctl", "-u", "glc", "--since", f"-{int(hours * 60)}min", "--no-pager", "-o", "short-iso"],
        capture_output=True, text=True, errors="replace").stdout
    last_t = None
    for raw in out.splitlines():
        if "[TCP] Sent " in raw or "[TCP] Included " in raw:
            continue
        m = TS.search(raw)
        if m:
            last_t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            yield last_t, m.group(2), m.group(3)
        elif "systemd[" in raw and ("Started" in raw or "Stopping" in raw or "Stopped" in raw):
            yield None, "SYSTEMD", raw
        elif "python[" in raw and last_t is not None:
            # Continuation line of a multi-line log message (crash reports).
            yield last_t, "CONT", raw.split("]: ", 1)[-1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    args = ap.parse_args(argv)

    names = {}                 # account id -> screen name
    addr_of = collections.defaultdict(list)   # screen name -> [(time, address)]
    crashes = collections.defaultdict(list)   # address -> [(time, summary)]
    crash_kinds = collections.Counter()
    current_crash = None
    addr_events = collections.defaultdict(list)   # address -> [(time, reason)]
    last_offer = {}            # account/screen name -> time of last "Offering X"
    drops = []                 # dicts
    open_drop = {}             # (game, account) -> drop
    restarts, errors = [], []
    pending_name = None

    for t, level, msg in read_log(args.hours):
        if level == "SYSTEMD":
            restarts.append(msg.strip())
            continue
        m = re.search(r"\[Gameplay\] Player (\S+) (?:made|sent|requests|Conceded)", msg)
        if m:
            pending_name = m.group(1)
        m = re.search(r"Received action from player ([0-9a-f-]{36})", msg)
        if m and pending_name:
            names[m.group(1)] = pending_name
            pending_name = None
        m = re.search(ADDR + r" User '([^']+)' successfully authenticated", msg)
        if m:
            addr_of[m.group(2)].append((t, m.group(1)))
        # Client crash reports: "[TCP] [addr] CLIENT CRASH REPORT" then lines.
        m = re.search(ADDR + r" CLIENT CRASH REPORT", msg)
        if m:
            current_crash = {"time": t, "addr": m.group(1), "lines": []}
            continue
        if current_crash is not None:
            if msg.startswith("=====") or msg.strip().startswith("=" * 10):
                if current_crash["lines"]:
                    text = " | ".join(current_crash["lines"])[:220]
                    crashes[current_crash["addr"]].append((current_crash["time"], text))
                    key = next((l for l in current_crash["lines"] if l.startswith("Stack")), text)[:120]
                    crash_kinds[key] += 1
                    current_crash = None
                continue
            line = msg.strip()
            if line and not line.startswith(("Log ID", "Debug Info")):
                current_crash["lines"].append(line.replace("Error Type : ", "").replace("Reason     :", "Reason:"))
            continue
        for pattern, reason in (
                (ADDR + r" Connection reset by peer", "player's connection reset"),
                (ADDR + r" Idle timeout", "idle timeout (no data from player for 4 min)"),
                (ADDR + r" Send drain timed out", "send timeout (player's connection too slow / stalled)"),
                (ADDR + r" Connection closed by client", "player's game closed the connection"),
                (ADDR + r" Error handling client: (.*)", "server error on connection"),
                (ADDR + r" Inbound rate limit hit", "rate limit")):
            m = re.search(pattern, msg)
            if m:
                addr_events[m.group(1)].append((t, reason))
        if "Evicting" in msg or "newest login" in msg.lower():
            m = re.search(ADDR, msg)
            if m:
                addr_events[m.group(1)].append((t, "replaced by a newer login"))
        m = re.search(GAME + r" Offering (\S+) \d+ legal", msg)
        if m:
            last_offer[m.group(2)] = t
        m = re.search(GAME + r" Player ([0-9a-f-]{36}) disconnected - detaching", msg)
        if m:
            game, acct = m.groups()
            d = {"time": t, "game": game, "account": acct, "outcome": "?", "back_after": None}
            drops.append(d)
            open_drop[(game, acct)] = d
        m = re.search(GAME + r" Player ([0-9a-f-]{36}) reconnecting", msg)
        if m and (m.group(1), m.group(2)) in open_drop:
            d = open_drop.pop((m.group(1), m.group(2)))
            d["outcome"] = "reconnected"
            d["back_after"] = (t - d["time"]).total_seconds()
        m = re.search(GAME + r" Reconnect grace expired for ([0-9a-f-]{36})", msg)
        if m and (m.group(1), m.group(2)) in open_drop:
            d = open_drop.pop((m.group(1), m.group(2)))
            d["outcome"] = "GAME LOST (didn't return in 60s)"
        m = re.search(GAME + r" Game over: (.*)", msg)
        if m:
            for key in [k for k in open_drop if k[0] == m.group(1)]:
                open_drop.pop(key)["outcome"] = "game ended while away: " + m.group(2)
        if (level in ("ERROR", "CRITICAL") or "Traceback" in msg) and current_crash is None and msg.strip() \
                and "CLIENT CRASH" not in msg and not msg.startswith(("Error Type", "Log ID", "Reason", "Debug Info", "  ", "=")):
            errors.append(f"{t}  {msg[:200]}")

    print(f"Mid-game disconnects in the last {args.hours:g} h: {len(drops)}\n")
    by_reason, by_player, by_hour, lost = (collections.Counter() for _ in range(4))
    for d in drops:
        name = names.get(d["account"], d["account"][:8])
        logins = [a for (lt, a) in addr_of.get(name, []) if lt <= d["time"]]
        addr = logins[-1] if logins else None
        reason = "no close reason logged (connection just dropped)"
        if addr:
            before = [r for (et, r) in addr_events.get(addr, []) if et and abs((et - d["time"]).total_seconds()) <= 5]
            if before:
                reason = before[-1]
        if any(d["time"] and "Stopping" in r for r in restarts):
            pass
        waited = last_offer.get(name)
        idle = f"{(d['time'] - waited).total_seconds():.0f}s after their last prompt" if waited and waited <= d["time"] else ""
        back = f" after {d['back_after']:.0f}s" if d["back_after"] is not None else ""
        same_second = sum(1 for o in drops if o["time"] == d["time"])
        cluster = f"  [{same_second} players dropped this second]" if same_second > 1 else ""
        print(f"{d['time']}  {name:<18} {reason:<55} -> {d['outcome']}{back}  {idle}  game {d['game'][:8]}{cluster}")
        for ct, text in crashes.get(addr, []) if addr else []:
            if 0 <= (d["time"] - ct).total_seconds() <= 120:
                print(f"      client error {(d['time'] - ct).total_seconds():.0f}s before: {text}")
        by_reason[reason] += 1
        by_player[name] += 1
        by_hour[d["time"].strftime("%H:00")] += 1
        if d["outcome"].startswith("GAME LOST"):
            lost[name] += 1

    print("\nBy reason:")
    for r, n in by_reason.most_common():
        print(f"  {n:4}  {r}")
    print("\nBy player (drops / games lost to a drop):")
    for p, n in by_player.most_common():
        print(f"  {n:4} / {lost[p]:<3} {p}")
    print("\nBy hour:")
    for h in sorted(by_hour):
        print(f"  {h}  {'#' * by_hour[h]} {by_hour[h]}")
    print("\nMost common client error reports (all players, whole window):")
    for k, n in crash_kinds.most_common(12):
        print(f"  {n:5}  {k}")
    print(f"\nServer starts/stops in window: {len(restarts)}")
    for r in restarts[-10:]:
        print("  " + r[:160])
    print(f"\nServer errors in window: {len(errors)}")
    for e in errors[-15:]:
        print("  " + e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
