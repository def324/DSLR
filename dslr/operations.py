from collections import namedtuple
from datetime import datetime
from time import time
from typing import List

from .config import settings
from .runner import exec

Snapshot = namedtuple("Snapshot", ["dbname", "name", "created_at"])


class DSLRException(Exception):
    pass


def get_snapshots() -> List[Snapshot]:
    """
    Returns the list of database snapshots

    Snapshots are databases that follow the naming convention:

    dslr_<timestamp>_<snapshot_name>
    """
    # Find the snapshot databases
    result = exec("psql", "-c", "SELECT datname FROM pg_database")

    if result.returncode != 0:
        raise DSLRException(result.stderr)

    lines = sorted(
        [
            line.strip()
            for line in result.stdout.split("\n")
            if line.strip().startswith("dslr_")
        ]
    )

    # Parse the name into a Snapshot
    parts = [line.split("_") for line in lines]
    return [
        Snapshot(
            dbname=line,
            name="_".join(part[2:]),
            created_at=datetime.fromtimestamp(int(part[1])),
        )
        for part, line in zip(parts, lines)
    ]


class SnapshotNotFound(Exception):
    pass


def find_snapshot(snapshot_name: str) -> Snapshot:
    """
    Returns the snapshot with the given name
    """
    snapshots = get_snapshots()

    try:
        return next(
            snapshot for snapshot in snapshots if snapshot.name == snapshot_name
        )
    except StopIteration as e:
        raise SnapshotNotFound(
            f'Snapshot with name "{snapshot_name}" does not exist.'
        ) from e


def create_snapshot(snapshot_name: str):
    """
    Takes a snapshot of the database

    Snapshotting works by creating a new database using the local database as a
    template.

        createdb -T source_db_name dslr_<timestamp>_<name>
    """
    result = exec(
        "createdb", "-T", settings.db.name, f"dslr_{round(time())}_{snapshot_name}"
    )

    if result.returncode != 0:
        raise DSLRException(result.stderr)


def delete_snapshot(snapshot: Snapshot):
    """
    Deletes the given snapshot
    """
    result = exec("dropdb", snapshot.dbname)

    if result.returncode != 0:
        raise DSLRException(result.stderr)


def restore_snapshot(snapshot: Snapshot):
    """
    Restores the database from the given snapshot
    """
    result = exec("dropdb", settings.db.name)

    if result.returncode != 0:
        raise DSLRException(result.stderr)

    result = exec("createdb", "-T", snapshot.dbname, settings.db.name)

    if result.returncode != 0:
        raise DSLRException(result.stderr)


def rename_snapshot(snapshot: Snapshot, new_name: str):
    """
    Renames the given snapshot
    """
    result = exec(
        "psql",
        "-c",
        f'ALTER DATABASE "{snapshot.dbname}" RENAME TO '
        f'"dslr_{round(snapshot.created_at.timestamp())}_{new_name}"',
    )

    if result.returncode != 0:
        raise DSLRException(result.stderr)


def export_snapshot(snapshot: Snapshot) -> str:
    """
    Exports the given snapshot to a file
    """
    export_path = f"{snapshot.name}_{snapshot.created_at:%Y%m%d-%H%M%S}.dump"
    result = exec("pg_dump", "-Fc", "-d", snapshot.dbname, "-f", export_path)

    if result.returncode != 0:
        raise DSLRException(result.stderr)

    return export_path
