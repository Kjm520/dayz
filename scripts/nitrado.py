"""
Nitrado: the server side of the deploy and survivor-board workflows. The Nitrado API for
restarts and server status, the FTP for pulling logs and uploading single files.

    python scripts/nitrado.py restart --note "deploy abc1234" --player-message "Restarting for a config update"
    python scripts/nitrado.py wait-started --timeout 10
    python scripts/nitrado.py logs list                      # names of the ADM and RPT files on the server
    python scripts/nitrado.py logs pull --adm nitrado-logs/adm --rpt /tmp/rpt --after before.txt --timeout 15
    python scripts/nitrado.py put remote/dayzxb_missions/dayzOffline.nasdara/db/messages.xml \
                                  /dayzxb_missions/dayzOffline.nasdara/db/messages.xml

Credentials come from the environment, never from arguments: NITRADO_SERVICE_TOKEN (a long-life
token with the "service" scope) for the API; FTP_HOST, FTP_PORT (optional, 21), FTP_USERNAME and
FTP_PASSWORD for the FTP. The workflows pass the repository secrets. Nothing here prints a
credential or a whole API reply: the gameserver details reply carries the FTP password.

The running instance writes its logs to a working copy that reaches FTP only when the instance
stops. `logs pull --after <listing>` therefore waits for an admin log that was not in a listing
taken before a restart, then pulls every ADM (and RPT) the local folder lacks or holds at a
different size. On timeout it warns and pulls what is there, so a job never fails for a slow sync.
"""
import argparse
import ftplib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("NITRADO_API", "https://api.nitrado.net")
LOG_DIR = "/dayzxb/config"
LOG_SUFFIXES = (".ADM", ".RPT")
STATUS_POLL_SECONDS = 10
FTP_POLL_SECONDS = 20


def env(name):
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"{name} is not set")
    return value


def warn(text):
    """A warning annotation on the run under GitHub Actions, a plain line anywhere else."""
    print(("::warning::" if os.environ.get("GITHUB_ACTIONS") else "warning: ") + text, flush=True)


# --- Nitrado API ----------------------------------------------------------------------------


def api(method, path, data=None):
    """One call; exits with the API's own message on any failure. Returns the parsed reply."""
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(
        API + path, data=body, method=method,
        headers={"Authorization": f"Bearer {env('NITRADO_SERVICE_TOKEN')}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("message", "")
        except ValueError:
            detail = ""
        sys.exit(f"Nitrado API {method} {path}: HTTP {e.code} {detail}".rstrip())
    if reply.get("status") != "success":
        sys.exit(f"Nitrado API {method} {path}: {reply.get('status')} {reply.get('message', '')}".rstrip())
    return reply


def service_id():
    """The one gameserver on the account; anything else is a configuration error."""
    services = api("GET", "/services")["data"]["services"]
    gameservers = [s for s in services if s.get("type") == "gameserver"]
    if len(gameservers) != 1:
        found = ", ".join(f"{s.get('id')} {s.get('type')} {s.get('details', {}).get('game')}" for s in services)
        sys.exit(f"expected exactly one gameserver on the account, found: {found or 'nothing'}")
    return gameservers[0]["id"]


def server_status(sid):
    return api("GET", f"/services/{sid}/gameservers")["data"]["gameserver"]["status"]


def cmd_restart(args):
    reply = api("POST", f"/services/{service_id()}/gameservers/restart",
                {"message": args.note, "restart_message": args.player_message})
    print(f"restart requested: {reply.get('message', 'ok')}")


def cmd_wait_started(args):
    """Poll until Nitrado reports the server started. Call it once the stop is known to have
    happened (a flushed log on FTP, or a restart requested long enough ago), since a restart
    that has not begun yet still reads as started."""
    sid = service_id()
    deadline = time.monotonic() + args.timeout * 60
    last = None
    while True:
        status = server_status(sid)
        if status != last:
            print(f"server status: {status}", flush=True)
            last = status
        if status == "started":
            return
        if time.monotonic() > deadline:
            sys.exit(f"server still {status} after {args.timeout} minutes")
        time.sleep(STATUS_POLL_SECONDS)


# --- FTP ------------------------------------------------------------------------------------


def ftp_connect():
    host = env("FTP_HOST")
    ftp = ftplib.FTP()
    try:
        ftp.connect(host, int(os.environ.get("FTP_PORT") or 21), timeout=60)
        ftp.login(env("FTP_USERNAME"), env("FTP_PASSWORD"))
    except ftplib.all_errors as e:
        sys.exit(f"FTP {host}: {e}")
    return ftp


def remote_logs(ftp):
    """{name: bytes} for every ADM and RPT file in the server's log folder."""
    names = [entry.rsplit("/", 1)[-1] for entry in ftp.nlst(LOG_DIR)]
    ftp.voidcmd("TYPE I")  # the listing switches the connection to ASCII; SIZE is a binary-mode command
    return {name: ftp.size(f"{LOG_DIR}/{name}") for name in names if name.upper().endswith(LOG_SUFFIXES)}


def is_adm(name):
    return name.upper().endswith(".ADM")


def pull_logs(ftp, remote, suffix, into):
    """Download the files with this suffix that are missing locally or differ in size."""
    os.makedirs(into, exist_ok=True)
    pulled = []
    for name, size in sorted(remote.items()):
        if not name.upper().endswith(suffix):
            continue
        target = os.path.join(into, name)
        if os.path.exists(target) and os.path.getsize(target) == size:
            continue
        with open(target, "wb") as f:
            ftp.retrbinary(f"RETR {LOG_DIR}/{name}", f.write)
        pulled.append(name)
        print(f"pulled {name} ({size} bytes)", flush=True)
    return pulled


def cmd_logs_list(args):
    with ftp_connect() as ftp:
        for name in sorted(remote_logs(ftp)):
            print(name)


def cmd_logs_pull(args):
    before = None
    if args.after:
        with open(args.after, encoding="utf-8") as f:
            before = {line.strip() for line in f if line.strip()}
    deadline = time.monotonic() + args.timeout * 60
    while True:
        with ftp_connect() as ftp:  # a fresh connection per poll; none is held open while waiting
            remote = remote_logs(ftp)
            fresh = sorted(n for n in remote if is_adm(n) and n not in before) if before is not None else []
            waiting = before is not None and not fresh and time.monotonic() < deadline
            if not waiting:
                if fresh:
                    print("new since the listing: " + ", ".join(fresh))
                elif before is not None:
                    warn(f"no new admin log reached FTP in {args.timeout:g} minutes; pulling what is there")
                pulled = pull_logs(ftp, remote, ".ADM", args.adm)
                if args.rpt:
                    pulled += pull_logs(ftp, remote, ".RPT", args.rpt)
        if not waiting:
            break
        print("waiting for the stopped instance's admin log to reach FTP ...", flush=True)
        time.sleep(FTP_POLL_SECONDS)
    print(f"{len(pulled)} file(s) pulled; the server holds {sum(map(is_adm, remote))} ADM and "
          f"{len(remote) - sum(map(is_adm, remote))} RPT")


def cmd_put(args):
    with ftp_connect() as ftp, open(args.local, "rb") as f:
        ftp.storbinary(f"STOR {args.remote}", f)
    print(f"uploaded {args.local} -> {args.remote}")


# --- main -----------------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("restart", help="restart the game server through the Nitrado API")
    p.add_argument("--note", default="restart", help="line for Nitrado's restart.log")
    p.add_argument("--player-message", default="Restarting", help="shown to players before the restart")
    p.set_defaults(func=cmd_restart)

    p = sub.add_parser("wait-started", help="wait until Nitrado reports the server started")
    p.add_argument("--timeout", type=float, default=10, help="minutes (default 10)")
    p.set_defaults(func=cmd_wait_started)

    logs = sub.add_parser("logs", help="the server's ADM and RPT files").add_subparsers(dest="action", required=True)
    p = logs.add_parser("list", help="print the names on the server, one per line")
    p.set_defaults(func=cmd_logs_list)
    p = logs.add_parser("pull", help="download what the local folders lack")
    p.add_argument("--adm", required=True, help="folder for the admin logs")
    p.add_argument("--rpt", help="folder for the RPT logs (not pulled without it)")
    p.add_argument("--after", metavar="LISTING", help="a `logs list` output taken before a restart: wait for an ADM not in it")
    p.add_argument("--timeout", type=float, default=15, help="minutes to wait with --after (default 15)")
    p.set_defaults(func=cmd_logs_pull)

    p = sub.add_parser("put", help="upload one file")
    p.add_argument("local")
    p.add_argument("remote", help="absolute path on the server")
    p.set_defaults(func=cmd_put)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
