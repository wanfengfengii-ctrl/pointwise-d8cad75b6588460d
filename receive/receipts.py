from dataclasses import dataclass

from capture.observation import Observation
from dispatch.request_ids import RequestIdentity
from receive.evidence import load_evidence
from station_store import atomic, require_text


class ReceiptNotFound(LookupError):
    pass


@dataclass(frozen=True)
class TransferReceipt:
    receipt_id: str
    identity: RequestIdentity
    episode: str
    observation: Observation


def initialize_receipts(db):
    db.execute('''CREATE TABLE IF NOT EXISTS transfer_receipts (
        receipt_id TEXT PRIMARY KEY, request_number TEXT NOT NULL UNIQUE REFERENCES inbox(request_number),
        episode TEXT NOT NULL UNIQUE REFERENCES inbox(episode))''')


def publish_receipt(db, evidence):
    identity = evidence.grant.identity
    receipt = TransferReceipt(identity.receipt_id, identity, identity.incoming_episode, evidence.observation)
    db.execute('INSERT INTO transfer_receipts VALUES (?, ?, ?)', (receipt.receipt_id, identity.number, receipt.episode))
    return receipt


def read_receipt(db, receipt_id):
    row = db.execute('SELECT request_number, episode FROM transfer_receipts WHERE receipt_id = ?', (receipt_id,)).fetchone()
    if row is None:
        raise ReceiptNotFound(receipt_id)
    number, episode = row
    evidence = load_evidence(db, number)
    return TransferReceipt(receipt_id, evidence.grant.identity, episode, evidence.observation)


def take_receipt(archives, station, receipt_id):
    require_text(receipt_id, 'receipt ID')
    with archives.open(station) as db, atomic(db, write=False):
        return read_receipt(db, receipt_id)
