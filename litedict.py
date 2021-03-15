from collections.abc import MutableMapping
import pathlib
import json
from typing import Callable
import sqlite3
from operator import itemgetter
from contextlib import contextmanager

# The __init__ function and the following imports are adapted
# from sqlite-utils by Simon Willison (@simonw)
# written under the Apache 2 LICENSE
# https://github.com/simonw/sqlite-utils/blob/main/sqlite_utils/db.py

try:
    import pysqlite3 as sqlite3
    import pysqlite3.dbapi2

    OperationalError = pysqlite3.dbapi2.OperationalError
except ImportError:
    import sqlite3

    OperationalError = sqlite3.OperationalError


__version__ = "0.2"

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
        filename_or_conn=None,
        memory=False,
        encoder: Callable = lambda x: json.dumps(x),
        decoder: Callable = lambda x: json.loads(x),
        **kwargs,
    ):
        assert (filename_or_conn is not None and not memory) or (
            filename_or_conn is None and memory
        ), "Either specify a filename_or_conn or pass memory=True"
        if memory or filename_or_conn == ":memory:":
            self.conn = sqlite3.connect(":memory:", isolation_level=None, **kwargs)
        elif isinstance(filename_or_conn, (str, pathlib.Path)):
            self.conn = sqlite3.connect(
                str(filename_or_conn), isolation_level=None, **kwargs
            )
        else:
            self.conn = filename_or_conn
            self.conn.isolation_level = None

        self.encoder = encoder
        self.decoder = decoder

        with transaction(self.conn) as c:
            # WITHOUT ROWID?
            c.execute(
                "CREATE TABLE IF NOT EXISTS Dict (key text NOT NULL PRIMARY KEY, value text)"
            )

        # if fast:
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
        return f"{type(self).__name__}(Connection={self.conn!r}, items={list(self.items())})"

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
