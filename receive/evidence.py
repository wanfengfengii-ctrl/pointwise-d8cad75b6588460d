from dataclasses import dataclass

from capture.observation import Observation
from dispatch.custody import TransferGrant
from dispatch.request_ids import RequestIdentity, TransferRejected
from station_store import bump_version, initialize_version, read_version


_AREA = 'evidence'


@dataclass(frozen=True)
class InboxFact:
    grant: TransferGrant
    observation: Observation
    active_link: bool


def initialize_evidence(db):
    db.execute('''CREATE TABLE IF NOT EXISTS inbox (
        request_number TEXT PRIMARY KEY, episode TEXT NOT NULL UNIQUE,
        identity TEXT NOT NULL, payload_digest TEXT NOT NULL, payload TEXT NOT NULL,
        active_link INTEGER NOT NULL DEFAULT 1 CHECK (active_link IN (0, 1)))''')
    initialize_version(db, _AREA)


def _fact(row):
    identity, digest, payload, active_link = row
    return InboxFact(TransferGrant(RequestIdentity.decode(identity), digest), Observation.decode(payload), bool(active_link))


def store_evidence(db, grant, observation):
    identity = grant.identity
    existing = load_evidence(db, identity.number)
    if existing is not None:
        if existing.grant != grant or existing.observation != observation:
            raise TransferRejected('isolated receipt conflicts with the existing original')
        return existing
    db.execute('''INSERT INTO inbox (request_number, episode, identity, payload_digest, payload)
                  VALUES (?, ?, ?, ?, ?)''', (
        identity.number, identity.incoming_episode, identity.encode(), grant.payload_digest, observation.encode(),
    ))
    bump_version(db, _AREA)
    return InboxFact(grant, observation, True)


def load_evidence(db, number):
    row = db.execute('''SELECT identity, payload_digest, payload, active_link
                        FROM inbox WHERE request_number = ?''', (number,)).fetchone()
    return None if row is None else _fact(row)


def remove_active_evidence_link(db, episode):
    changed = db.execute('UPDATE inbox SET active_link = 0 WHERE episode = ? AND active_link = 1', (episode,))
    if changed.rowcount:
        bump_version(db, _AREA)
    return bool(changed.rowcount)


def list_inbox_facts(db):
    return tuple(_fact(row) for row in db.execute('SELECT identity, payload_digest, payload, active_link FROM inbox'))


def read_evidence_version(db):
    return read_version(db, _AREA)
