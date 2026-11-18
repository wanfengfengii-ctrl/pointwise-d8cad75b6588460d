from dataclasses import dataclass

from dispatch.custody import TransferGrant
from dispatch.request_ids import RequestIdentity, TransferRejected
from receive.evidence import load_evidence
from receive.receipts import ReceiptNotFound, publish_receipt, read_receipt
from station_store import atomic, bump_version, initialize_version, read_version


_AREA = 'incoming'


@dataclass(frozen=True)
class IncomingDecision:
    grant: TransferGrant
    episode: str
    receipt_id: str


def initialize_incoming(db):
    db.execute('''CREATE TABLE IF NOT EXISTS incoming_decisions (
        request_number TEXT PRIMARY KEY REFERENCES inbox(request_number),
        identity TEXT NOT NULL, payload_digest TEXT NOT NULL,
        episode TEXT NOT NULL UNIQUE REFERENCES inbox(episode),
        receipt_id TEXT NOT NULL UNIQUE REFERENCES transfer_receipts(receipt_id))''')
    initialize_version(db, _AREA)


def _decision(row):
    identity, digest, episode, receipt_id = row
    return IncomingDecision(TransferGrant(RequestIdentity.decode(identity), digest), episode, receipt_id)


def lookup_incoming_decision(db, number):
    row = db.execute('''SELECT identity, payload_digest, episode, receipt_id
                        FROM incoming_decisions WHERE request_number = ?''', (number,)).fetchone()
    return None if row is None else _decision(row)


def admit_received(db, evidence):
    grant = evidence.grant
    identity = grant.identity
    previous = lookup_incoming_decision(db, identity.number)
    if previous is not None:
        if previous.grant != grant:
            raise TransferRejected('admission already belongs to a different grant')
        return
    if not evidence.active_link:
        raise TransferRejected('the received copy has been retired')
    try:
        receipt = read_receipt(db, identity.receipt_id)
    except ReceiptNotFound:
        receipt = publish_receipt(db, evidence)
    db.execute('INSERT INTO incoming_decisions VALUES (?, ?, ?, ?, ?)', (
        identity.number, identity.encode(), grant.payload_digest, receipt.episode, receipt.receipt_id,
    ))
    bump_version(db, _AREA)


def settle_incoming(archives, grant, *, before_commit=None):
    identity = grant.identity
    with archives.open(identity.destination) as db, atomic(db):
        admission = lookup_incoming_decision(db, identity.number)
        if admission is None or admission.grant != grant:
            raise TransferRejected('no admitted original matches this grant')
        receipt = read_receipt(db, admission.receipt_id)
        if before_commit is not None:
            before_commit()
        return receipt


def list_incoming_facts(db):
    return tuple(_decision(row) for row in db.execute(
        'SELECT identity, payload_digest, episode, receipt_id FROM incoming_decisions'))


def admitted_episodes(inbox, decisions):
    evidence_by_number = {fact.grant.identity.number: fact for fact in inbox}
    for decision in decisions:
        identity = decision.grant.identity
        fact = evidence_by_number.get(identity.number)
        if fact is None or fact.grant != decision.grant or decision.episode != identity.incoming_episode:
            raise TransferRejected('decision cannot be matched to its admitted original')
        yield decision, fact


def load_admitted_observation(db, record_id, episode):
    row = db.execute('''SELECT identity, payload_digest, episode, receipt_id
                        FROM incoming_decisions WHERE episode = ?''', (episode,)).fetchone()
    if row is None:
        return None
    decision = _decision(row)
    identity = decision.grant.identity
    evidence = load_evidence(db, identity.number)
    if identity.record_id != record_id or evidence is None or evidence.grant != decision.grant or not evidence.active_link:
        return None
    return evidence.observation


def read_incoming_version(db):
    return read_version(db, _AREA)


def release_admission(db, episode):
    changed = db.execute('DELETE FROM incoming_decisions WHERE episode = ?', (episode,))
    if changed.rowcount:
        bump_version(db, _AREA)
