from dataclasses import dataclass
import json

from capture.observation import Observation, Origin
from capture.validation import ObservationRejected
from station_store import bump_version, initialize_version, read_version


_AREA = 'origin'


@dataclass(frozen=True)
class OriginFact:
    episode: str
    origin: Origin
    observation: Observation | None


def initialize_recordings(db):
    db.execute('''CREATE TABLE IF NOT EXISTS origin_records (
        record_id TEXT PRIMARY KEY, episode TEXT NOT NULL UNIQUE,
        shift TEXT NOT NULL, origin TEXT NOT NULL, payload TEXT)''')
    db.execute('CREATE INDEX IF NOT EXISTS origin_by_shift ON origin_records (shift)')
    initialize_version(db, _AREA)


def insert_observation(db, observation):
    encoded = observation.encode()
    previous = db.execute('SELECT payload FROM origin_records WHERE record_id = ?', (observation.record_id,)).fetchone()
    if previous is not None:
        if previous[0] is None:
            raise ObservationRejected('the original slot has been retired')
        if previous[0] != encoded:
            raise ObservationRejected('the original slot is already occupied by different data')
        return Observation.decode(previous[0])
    db.execute('INSERT INTO origin_records VALUES (?, ?, ?, ?, ?)', (
        observation.record_id, observation.episode, observation.origin.shift,
        json.dumps(observation.origin.to_data(), separators=(',', ':')), encoded,
    ))
    bump_version(db, _AREA)
    return observation


def load_observation(db, record_id, episode):
    row = db.execute('''SELECT payload FROM origin_records
                        WHERE record_id = ? AND episode = ?''', (record_id, episode)).fetchone()
    if row is None or row[0] is None:
        return None
    return Observation.decode(row[0])


def list_origin_facts(db, shift):
    rows = db.execute('SELECT episode, origin, payload FROM origin_records WHERE shift = ?', (shift,))
    return tuple(OriginFact(episode, Origin(*json.loads(origin)),
                            Observation.decode(payload) if payload is not None else None)
                 for episode, origin, payload in rows)


def read_origin_version(db):
    return read_version(db, _AREA)


def remove_origin_payload(db, record_id, episode):
    change = db.execute('''UPDATE origin_records SET payload = NULL
                           WHERE record_id = ? AND episode = ? AND payload IS NOT NULL''', (record_id, episode))
    if change.rowcount:
        bump_version(db, _AREA)
    return bool(change.rowcount)
