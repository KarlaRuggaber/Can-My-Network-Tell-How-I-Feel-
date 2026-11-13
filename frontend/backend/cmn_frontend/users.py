"""Manage logins of the results portal (stored in <CMN_HOME>/users.json, default ~/cmn-data/frontend).

    python -m cmn_frontend.users list
    python -m cmn_frontend.users add anna --role single --profile ben
    python -m cmn_frontend.users add dr-meier --role multi --profiles all
    python -m cmn_frontend.users add parent --role multi --profiles maria,carl
    python -m cmn_frontend.users passwd anna
    python -m cmn_frontend.users remove anna

The password is asked for interactively (or read from stdin with --password-stdin).
"""

from __future__ import annotations

import argparse
import getpass
import sys

from .auth import ROLES, UserStore
from .profiles import ProfileStore
from .settings import load_settings


def _password(args) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Repeat: "):
        raise SystemExit("passwords differ")
    return pw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cmn_frontend.users", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("add")
    a.add_argument("username")
    a.add_argument("--role", choices=ROLES, required=True)
    a.add_argument("--profile", help="profile id (single-profile user)")
    a.add_argument("--profiles", help="comma-separated profile ids, or 'all' (multi-profile user)")
    a.add_argument("--password-stdin", action="store_true")
    p = sub.add_parser("passwd")
    p.add_argument("username")
    p.add_argument("--password-stdin", action="store_true")
    r = sub.add_parser("remove")
    r.add_argument("username")
    args = ap.parse_args(argv)

    s = load_settings()
    users = UserStore(s.home_dir)
    if args.cmd == "list":
        for u in users.all():
            print(f"{u.username:20} {u.role:7} {','.join(u.profiles)}")
        return 0
    if args.cmd == "add":
        known = {p.id for p in ProfileStore(s).all()}
        if args.role == "single":
            ids = [args.profile] if args.profile else []
        else:
            ids = ["*"] if (args.profiles or "all") == "all" else [x.strip() for x in args.profiles.split(",") if x.strip()]
        unknown = [i for i in ids if i != "*" and i not in known]
        if unknown:
            raise SystemExit(f"unknown profile(s): {', '.join(unknown)}; known: {', '.join(sorted(known))}")
        users.add(args.username, _password(args), args.role, ids)
        print(f"added {args.username} ({args.role}: {','.join(ids)})")
        return 0
    if args.cmd == "passwd":
        users.set_password(args.username, _password(args))
        print("password changed")
        return 0
    if args.cmd == "remove":
        print("removed" if users.remove(args.username) else "no such user")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
