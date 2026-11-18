from capture.observation import origin_episode
from capture.recordings import remove_origin_payload
from dispatch.custody import mark_retired, outgoing_status
from dispatch.request_ids import TransferRejected
from receive.receipts import ReceiptNotFound, take_receipt
from receive.evidence import remove_active_evidence_link
from station_store import atomic


def retire(archives, station, episode, receipt_id):
    with archives.open(station) as db:
        fact = outgoing_status(db, episode)
    if fact is None:
        raise TransferRejected('unknown source episode')
    grant = fact.grant
    identity = grant.identity
    if receipt_id != identity.receipt_id:
        raise TransferRejected('receipt does not belong to this source episode')
    try:
        receipt = take_receipt(archives, identity.destination, receipt_id)
    except ReceiptNotFound as error:
        raise TransferRejected('the source episode has no committed receipt') from error
    if receipt.identity != identity or receipt.observation.digest() != grant.payload_digest:
        raise TransferRejected('receipt does not match the authorized original')

    with archives.open(station) as db, atomic(db):
        confirmed = outgoing_status(db, episode)
        if confirmed is None or confirmed.grant != grant:
            raise TransferRejected('source grant has changed')
        if confirmed.retired:
            return
        if episode == origin_episode(identity.record_id):
            removed = remove_origin_payload(db, identity.record_id, episode)
        else:
            removed = remove_active_evidence_link(db, episode)
        if not removed:
            raise TransferRejected('source copy is unavailable for this episode')
        mark_retired(db, grant, receipt_id)
