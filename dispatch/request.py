from dispatch.custody import outgoing_status, reserve_episode
from dispatch.request_ids import RequestIdentity, TransferRejected, bind_request_number, find_request_identity
from dispatch.retry import load_source_payload, resume_request, run_checkpoint
from station_store import atomic


def _source_state(db, identity):
    reserved = outgoing_status(db, identity.episode)
    if reserved is not None:
        if reserved.grant.identity != identity:
            raise TransferRejected('episode is already reserved for a different request')
        return reserved.grant, None
    observation = load_source_payload(db, identity)
    if observation is None:
        raise TransferRejected('the source does not hold the specified current episode')
    return None, observation


def transfer_request(archives, identity, *, checkpoint=None):
    if not isinstance(identity, RequestIdentity):
        raise TransferRejected('a complete RequestIdentity is required')
    with archives.open(archives.request_home) as db:
        known = find_request_identity(db, identity.number)
    if known is not None and known != identity:
        raise TransferRejected('request number is bound to different parameters')

    if known is None:
        with archives.open(identity.source) as db, atomic(db, write=False):
            _source_state(db, identity)
        with archives.open(archives.request_home) as db, atomic(db):
            bind_request_number(db, identity)

    with archives.open(identity.source) as db, atomic(db):
        grant, observation = _source_state(db, identity)
        if grant is None:
            grant = reserve_episode(db, identity, observation)
    run_checkpoint(checkpoint, 'after_grant')
    return resume_request(archives, grant, checkpoint=checkpoint)
