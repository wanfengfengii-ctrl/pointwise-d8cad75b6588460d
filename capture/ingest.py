from capture.calibration import load_calibration
from capture.observation import Observation, Origin
from capture.recordings import insert_observation
from capture.validation import ObservationRejected, validate_record_input
from station_store import atomic, require_text


def record(archives, station, shift, recording, instrument, slot, revision, pulses):
    try:
        origin = Origin(station, shift, recording, instrument, slot)
        require_text(revision, 'revision')
    except ValueError as error:
        raise ObservationRejected(str(error)) from error
    with archives.open(station) as db, atomic(db):
        calibration = load_calibration(db, instrument, revision)
        validate_record_input(instrument, slot, calibration, pulses)
        return insert_observation(db, Observation(origin, calibration, pulses))
