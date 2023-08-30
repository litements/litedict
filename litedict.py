from collections.abc import MutableMapping
import pathlib
import json
from typing import Callable
import logging
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


__version__ = "0.5"


class SQLDict(MutableMapping):
    def __init__(
        self,
        filename_or_conn=None,
        memory=False,
        writeback=False,
        encoder: Callable = lambda x: json.dumps(x),
        decoder: Callable = lambda x: json.loads(x),
        **kwargs,
    ):

        self.conn: sqlite3.Connection

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
            assert self.conn
            self.conn.isolation_level = None

        self.encoder = encoder
        self.decoder = decoder
        self.writeback = writeback
        self._writeback = {}

        # store kwargs to pass them to new connections (used during backups)
        self._init_kwargs = kwargs

        with self.transaction():
            # WITHOUT ROWID?
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS Dict (key text NOT NULL PRIMARY KEY, value)"
            )

        # if fast:
        self.conn.execute("PRAGMA journal_mode = 'WAL';")
        self.conn.execute("PRAGMA temp_store = 2;")
        self.conn.execute("PRAGMA synchronous = 1;")
        self.conn.execute(f"PRAGMA cache_size = {-1 * 64_000};")

    def __setitem__(self, key, value):
        if self.writeback:
            self._writeback[key] = value
        self.conn.execute(
            "INSERT OR REPLACE INTO  Dict VALUES (?, ?)", (key, self.encoder(value))
        )

    def __getitem__(self, key):
        try:
            value = self._writeback[key]
        except KeyError:
            c = self.conn.execute("SELECT value FROM Dict WHERE Key=?", (key,))
            row = c.fetchone()
            if row is None:
                raise KeyError(key)
            value = self.decoder(row[0])
            if self.writeback:
                self._writeback[key] = value
        return value

    def __delitem__(self, key):
        self._writeback.pop(key,None) # Will not fail even if missing
        if key not in self:
            raise KeyError(key)
        

        self.conn.execute("DELETE FROM Dict WHERE key=?", (key,))

    def __len__(self):
        return next(self.conn.execute("SELECT COUNT(*) FROM Dict"))[0]

    def __iter__(self):
        for row in self.conn.execute("SELECT key FROM Dict"):
            yield row[0]

    def keys(self):
        for row in self.conn.execute("SELECT key FROM Dict"):
            yield row[0]

    def values(self):
        for row in self.conn.execute("SELECT value FROM Dict"):
            yield self.decoder(row[0])

    def items(self):
        c = self.conn.execute("SELECT key, value FROM Dict")
        for row in c:
            yield (row[0], self.decoder(row[1]))

    def __repr__(self):
        return f"{type(self).__name__}(Connection={self.conn!r}, items={len(self)})"

    def glob(self, pat: str):
        c = self.conn.execute("SELECT Key FROM Dict WHERE Key GLOB ?", (pat,))
        keys = c.fetchall()
        if keys is None:
            raise KeyError(pat)
        return [self[key[0]] for key in keys]
    
    def sync(self):
        for key,val in self._writeback.items():
            self[key] = val

    # SQLite works better in autocommit mode when using short DML (INSERT / UPDATE / DELETE) statements
    # source: https://charlesleifer.com/blog/going-fast-with-sqlite-and-python/
    @contextmanager
    def transaction(self, mode="DEFERRED"):

        if mode not in {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}:
            raise ValueError(f"Transaction mode '{mode}' is not valid")
        # We must issue a "BEGIN" explicitly when running in auto-commit mode.
        self.conn.execute(f"BEGIN {mode}")
        try:
            # Yield control back to the caller.
            yield
        except BaseException:
            self.conn.rollback()  # Roll back all changes if an exception occurs.
            raise
        else:
            self.conn.commit()

    def to_memory(self):
        """
        Copy to memory.

        This closes the current connection and substitutes
        it with another in-memory one.
        """

        def progress(status, remaining, total):
            logging.info(f"Copied {total-remaining} of {total} pages...")

        dest = sqlite3.connect(":memory:", isolation_level=None, **self._init_kwargs)
        self.conn.backup(dest, progress=progress)
        self.conn.close()
        self.conn = dest
        return self

    def to_disk(self, new_db_or_conn):
        """
        Copy to disk file.

        This closes the current connection and substitutes
        it with another file-based one.
        """

        def progress(status, remaining, total):
            logging.info(f"Copied {total-remaining} of {total} pages...")

        dest = sqlite3.connect(
            new_db_or_conn, isolation_level=None, **self._init_kwargs
        )
        self.conn.backup(dest, progress=progress)
        self.conn = dest
        return self

    def vacuum(self):
        self.conn.execute("VACUUM;")

    def close(self):
        self.sync()
        self.conn.close()
