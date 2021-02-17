from collections.abc import MutableMapping
import json
import pprint
from typing import Callable, Tuple, Dict
import sqlite3
from operator import itemgetter
from contextlib import contextmanager

__version__ = "0.1.1"

# SQLite works better in autocommit mode when using short DML (INSERT / UPDATE / DELETE) statements
# source: https://charlesleifer.com/blog/going-fast-with-sqlite-and-python/
@contextmanager
def transaction(conn: sqlite3.Connection):
    # We must issue a "BEGIN" explicitly when running in auto-commit mode.
    conn.execute("BEGIN")
    try:
        # Yield control back to the caller.
        yield conn
    except:
        conn.rollback()  # Roll back all changes if an exception occurs.
        raise
    else:
        conn.commit()


class SQLDict(MutableMapping):
    def __init__(
        self,
        dbname,
        check_same_thread=False,
        fast=True,
        encoder: Callable = lambda x: json.dumps(x),
        decoder: Callable = lambda x: json.loads(x),
        **kwargs,
    ):
        self.dbname = dbname

        self.conn = sqlite3.connect(
            self.dbname,
            check_same_thread=check_same_thread,
            isolation_level=None,
            **kwargs,
        )
        self.encoder = encoder
        self.decoder = decoder

        with transaction(self.conn) as c:
            # WITHOUT ROWID?
            c.execute(
                "CREATE TABLE IF NOT EXISTS Dict (key text NOT NULL PRIMARY KEY, value text)"
            )

        if fast:
            self.conn.execute("PRAGMA journal_mode = 'WAL';")
            self.conn.execute("PRAGMA temp_store = 2;")
            self.conn.execute("PRAGMA synchronous = 1;")
            self.conn.execute(f"PRAGMA cache_size = {-1 * 64_000};")

    def __setitem__(self, key, value):

        self.conn.execute(
            "INSERT OR REPLACE INTO  Dict VALUES (?, ?)", (key, self.encoder(value))
        )

    def __getitem__(self, key):
        c = self.conn.execute("SELECT value FROM Dict WHERE Key=?", (key,))
        row = c.fetchone()
        if row is None:
            raise KeyError(key)
        return self.decoder(row[0])

    def __delitem__(self, key):

        if key not in self:
            raise KeyError(key)

        self.conn.execute("DELETE FROM Dict WHERE key=?", (key,))

    def __len__(self):
        return next(self.conn.execute("SELECT COUNT(*) FROM Dict"))[0]

    def __iter__(self):
        c = self.conn.execute("SELECT key FROM Dict")
        return map(itemgetter(0), c.fetchall())

    def __repr__(self):
        return (
            f"{type(self).__name__}(dbname={self.dbname!r}, items={list(self.items())})"
        )

    def glob(self, pat: str):
        c = self.conn.execute("SELECT value FROM Dict WHERE Key GLOB ?", (pat,))
        rows = c.fetchall()
        if rows is None:
            raise KeyError(pat)
        return [self.decoder(x[0]) for x in rows]

    def vacuum(self):
        self.conn.execute("VACUUM;")

    def close(self):
        self.conn.close()
