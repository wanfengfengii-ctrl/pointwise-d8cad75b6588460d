from dataclasses import dataclass

from dispatch.request_ids import RequestIdentity, TransferRejected
from station_store import bump_version, initialize_version, read_version


_AREA = 'outgoing'


@dataclass(frozen=True)
class TransferGrant:
    identity: RequestIdentity
    payload_digest: str


@dataclass(frozen=True)
class OutgoingFact:
    grant: TransferGrant
    recorded_receipt: str | None
    retired: bool

    def ended_by(self, terminal_grant):
        return terminal_grant == self.grant


def initialize_outgoing(db):
    db.execute('''CREATE TABLE IF NOT EXISTS outgoing (
        episode TEXT PRIMARY KEY, request_number TEXT NOT NULL UNIQUE,
        identity TEXT NOT NULL, payload_digest TEXT NOT NULL,
        recorded_receipt TEXT, retired INTEGER NOT NULL DEFAULT 0 CHECK (retired IN (0, 1)))''')
    initialize_version(db, _AREA)


def _fact(row):
    identity, digest, receipt, retired = row
    return OutgoingFact(TransferGrant(RequestIdentity.decode(identity), digest), receipt, bool(retired))


def outgoing_status(db, episode):
    row = db.execute('''SELECT identity, payload_digest, recorded_receipt, retired
                        FROM outgoing WHERE episode = ?''', (episode,)).fetchone()
    return None if row is None else _fact(row)


def reserve_episode(db, identity, observation):
    if observation.record_id != identity.record_id:
        raise TransferRejected('grant payload belongs to another record')
    grant = TransferGrant(identity, observation.digest())
    previous = outgoing_status(db, identity.episode)
    if previous is not None:
        if previous.grant != grant:
            raise TransferRejected('episode already has a different grant')
        return previous.grant
    db.execute('''INSERT INTO outgoing (episode, request_number, identity, payload_digest)
                  VALUES (?, ?, ?, ?)''', (identity.episode, identity.number, identity.encode(), grant.payload_digest))
    bump_version(db, _AREA)
    return grant


def record_result(db, grant, receipt_id):
    identity = grant.identity
    fact = outgoing_status(db, identity.episode)
    if fact is None or fact.grant != grant or receipt_id != identity.receipt_id:
        raise TransferRejected('result does not match the source grant')
    if fact.recorded_receipt is None:
        db.execute('UPDATE outgoing SET recorded_receipt = ? WHERE episode = ?', (receipt_id, identity.episode))
        bump_version(db, _AREA)
    elif fact.recorded_receipt != receipt_id:
        raise TransferRejected('source episode has a different recorded result')


def mark_retired(db, grant, receipt_id):
    record_result(db, grant, receipt_id)
    changed = db.execute('UPDATE outgoing SET retired = 1 WHERE episode = ? AND retired = 0',
                         (grant.identity.episode,))
    if changed.rowcount:
        bump_version(db, _AREA)


def list_outgoing_facts(db):
    rows = db.execute('SELECT identity, payload_digest, recorded_receipt, retired FROM outgoing')
    return tuple(_fact(row) for row in rows)


def read_outgoing_version(db):
    return read_version(db, _AREA)
