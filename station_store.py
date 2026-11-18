from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3


STATIONS = ('east', 'west')


def require_text(value, name):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{name} must be nonempty text without NUL')
    return value


def require_station(value):
    if value not in STATIONS:
        raise ValueError(f'unknown station: {value!r}')
    return value


@contextmanager
def atomic(db, *, write=True):
    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def initialize_version(db, area):
    db.execute('CREATE TABLE IF NOT EXISTS fact_versions (area TEXT PRIMARY KEY, version INTEGER NOT NULL)')
    db.execute('INSERT OR IGNORE INTO fact_versions VALUES (?, 0)', (area,))


def read_version(db, area):
    return db.execute('SELECT version FROM fact_versions WHERE area = ?', (area,)).fetchone()[0]


def bump_version(db, area):
    db.execute('UPDATE fact_versions SET version = version + 1 WHERE area = ?', (area,))


@dataclass(frozen=True)
class Archives:
    east_path: Path
    west_path: Path
    request_home: str = 'east'

    def __post_init__(self):
        for field in ('east_path', 'west_path'):
            object.__setattr__(self, field, Path(getattr(self, field)).resolve())
        if self.east_path == self.west_path:
            raise ValueError('the two stations require separate databases')
        require_station(self.request_home)

    def path(self, station):
        require_station(station)
        return self.east_path if station == 'east' else self.west_path

    @contextmanager
    def _connect(self, station, *, create=False):
        mode = 'rwc' if create else 'rw'
        db = sqlite3.connect(f'{self.path(station).as_uri()}?mode={mode}', uri=True, isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys = ON')
            yield db
        finally:
            db.close()

    def _check_identity(self, db, station):
        identity = db.execute('SELECT station, request_home FROM archive_identity WHERE singleton = 1').fetchone()
        if identity != (station, self.request_home):
            raise ValueError(f'database configuration mismatch for {station}')

    @contextmanager
    def open(self, station):
        with self._connect(station) as db:
            self._check_identity(db, station)
            yield db

    def initialize_station(self, station):
        from capture.calibration import initialize_calibrations
        from capture.recordings import initialize_recordings
        from dispatch.custody import initialize_outgoing
        from dispatch.request_ids import initialize_request_ids
        from edition.storage import initialize_editions
        from receive.custody import initialize_incoming
        from receive.evidence import initialize_evidence
        from receive.receipts import initialize_receipts

        with self._connect(station, create=True) as db, atomic(db):
            db.execute('''CREATE TABLE IF NOT EXISTS archive_identity (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                station TEXT NOT NULL, request_home TEXT NOT NULL)''')
            db.execute('INSERT OR IGNORE INTO archive_identity VALUES (1, ?, ?)', (station, self.request_home))
            self._check_identity(db, station)
            initialize_calibrations(db)
            initialize_recordings(db)
            if station == self.request_home:
                initialize_request_ids(db)
            initialize_outgoing(db)
            initialize_evidence(db)
            initialize_receipts(db)
            initialize_incoming(db)
            initialize_editions(db)

    def initialize(self):
        for station in STATIONS:
            self.initialize_station(station)
