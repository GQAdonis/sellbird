"""``sellbird storage``: apply, inspect and (as an operator) reverse Postgres migrations.

Migrations run with the migration role's connection string, never the app's:
``SELLBIRD_MIGRATE_DATABASE_URL`` when set, else ``SELLBIRD_DATABASE_URL`` (the
migration Job receives the migration role's string under that name; the app
container never does). ``--dsn-env`` names another variable. The connection
string is never printed.
"""

from __future__ import annotations

import os
import sys

MIGRATE_ENV = "SELLBIRD_MIGRATE_DATABASE_URL"
RUNTIME_ENV = "SELLBIRD_DATABASE_URL"


def _dsn(args) -> tuple[str, str]:
    """(variable name, connection string) to migrate with, or exit with why."""
    names = [args.dsn_env] if args.dsn_env else [MIGRATE_ENV, RUNTIME_ENV]
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            if not value.startswith(("postgresql://", "postgres://")):
                sys.exit(f"\n  {name} isn't a postgresql:// connection string.\n")
            return name, value
    sys.exit(f"\n  Set {' or '.join(names)} to the migration role's connection string.\n")


def cmd_storage(args) -> None:
    from importlib.util import find_spec

    if find_spec("psycopg") is None:
        sys.exit("\n  Postgres support isn't installed: pip install 'sellbird[postgres]'\n")
    from sellbird.storage_postgres import migrate

    action = args.storage_action or "status"
    name, dsn = _dsn(args)
    try:
        if action == "migrate":
            done = migrate.migrate_up(dsn, target=args.to)
            state = migrate.status(dsn)
            if done:
                for m in done:
                    print(f"  applied {m.version:04d} {m.name}")
            print(f"\n  Schema at version {state.current} of {state.latest} (using {name}).\n")
        elif action == "down":
            if args.to is None or not args.yes:
                sys.exit("\n  Going down drops tables and their rows. Run again with "
                         "--to VERSION --yes once you mean it.\n")
            for m in migrate.migrate_down(dsn, target=args.to):
                print(f"  reverted {m.version:04d} {m.name}")
            state = migrate.status(dsn)
            print(f"\n  Schema at version {state.current} of {state.latest} (using {name}).\n")
        else:
            state = migrate.status(dsn)
            print(f"\n  Schema at version {state.current} of {state.latest}; "
                  f"{state.pending} pending (using {name}).\n")
    except migrate.MigrationError as e:
        sys.exit(f"\n  {e}\n")


def register(subparsers) -> None:
    sub = subparsers.add_parser(
        "storage", help="Postgres schema: migrate (migration role), status, down")
    sub.add_argument("storage_action", nargs="?", default="status",
                     choices=["migrate", "status", "down"])
    sub.add_argument("--to", type=int, default=None,
                     help="migrate: stop at this version; down: go back to this version")
    sub.add_argument("--yes", action="store_true", help="down: confirm dropping tables")
    sub.add_argument("--dsn-env", default="",
                     help=f"read the connection string from this variable (default "
                          f"{MIGRATE_ENV}, then {RUNTIME_ENV})")
    sub.set_defaults(func=cmd_storage)
