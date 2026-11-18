from capture.observation import Observation
from capture.validation import ObservationRejected, validate_record_input
from dispatch.custody import outgoing_status
from dispatch.request_ids import TransferRejected
from receive.evidence import store_evidence
from station_store import atomic


def validate_envelope(destination, grant, observation):
    identity = grant.identity
    if identity.destination != destination:
        raise TransferRejected('grant targets a different station')
    if not isinstance(observation, Observation) or observation.record_id != identity.record_id:
        raise TransferRejected('envelope does not carry the authorized record')
    origin = observation.origin
    try:
        validate_record_input(origin.instrument, origin.slot, observation.calibration, observation.pulses)
    except ObservationRejected as error:
        raise TransferRejected('invalid observation in transfer envelope') from error
    if observation.digest() != grant.payload_digest:
        raise TransferRejected('observation differs from the source grant')


def accept_original(archives, grant, observation):
    identity = grant.identity
    validate_envelope(identity.destination, grant, observation)
    with archives.open(identity.source) as db:
        source = outgoing_status(db, identity.episode)
    if source is None or source.grant != grant:
        raise TransferRejected('envelope has no matching durable source grant')
    with archives.open(identity.destination) as db, atomic(db):
        return store_evidence(db, grant, observation)
