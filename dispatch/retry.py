from capture.observation import origin_episode
from capture.recordings import load_observation
from dispatch.custody import TransferGrant, outgoing_status, record_result
from dispatch.request_ids import TransferRejected
from receive.accept import accept_original
from receive.custody import load_admitted_observation, release_admission, settle_incoming
from receive.receipts import ReceiptNotFound, take_receipt
from station_store import atomic


class TransferInterrupted(RuntimeError):
    pass


def run_checkpoint(checkpoint, stage):
    if checkpoint is not None:
        checkpoint(stage)


def load_source_payload(db, identity):
    if identity.episode == origin_episode(identity.record_id):
        return load_observation(db, identity.record_id, identity.episode)
    return load_admitted_observation(db, identity.record_id, identity.episode)


def apply_transfer_result(archives, receipt):
    identity = receipt.identity
    try:
        fixed_receipt = take_receipt(archives, identity.destination, receipt.receipt_id)
    except ReceiptNotFound as error:
        raise TransferRejected('result has no receiver receipt') from error
    if fixed_receipt != receipt:
        raise TransferRejected('result differs from the fixed receipt')
    grant = TransferGrant(identity, receipt.observation.digest())
    with archives.open(identity.source) as db, atomic(db):
        record_result(db, grant, receipt.receipt_id)
        release_admission(db, identity.episode)
    return fixed_receipt


def resume_request(archives, grant, *, checkpoint=None):
    identity = grant.identity
    with archives.open(identity.source) as db, atomic(db, write=False):
        fact = outgoing_status(db, identity.episode)
        if fact is None or fact.grant != grant:
            raise TransferRejected('source grant is unavailable')
        recorded_receipt = fact.recorded_receipt
        observation = None if recorded_receipt is not None else load_source_payload(db, identity)
    if recorded_receipt is not None:
        try:
            receipt = take_receipt(archives, identity.destination, recorded_receipt)
        except ReceiptNotFound as error:
            raise TransferRejected('the recorded result is unavailable at the destination') from error
        if receipt.identity != identity or receipt.observation.digest() != grant.payload_digest:
            raise TransferRejected('the recorded result does not match the source grant')
        return receipt
    if observation is None:
        raise TransferInterrupted('source original is unavailable for delivery')
    accept_original(archives, grant, observation)
    run_checkpoint(checkpoint, 'after_receipt')
    receipt = settle_incoming(archives, grant, before_commit=lambda: run_checkpoint(checkpoint, 'before_decision_commit'))
    run_checkpoint(checkpoint, 'before_reply')
    return apply_transfer_result(archives, receipt)
