from capture.calibration import CalibrationRevision


class ObservationRejected(ValueError):
    pass


def validate_reading(pulses):
    if pulses is not None and (type(pulses) is not int or pulses < 0):
        raise ObservationRejected('pulses must be a nonnegative integer or None')


def validate_record_input(instrument, slot, calibration, pulses):
    if type(slot) is not int or slot < 0:
        raise ObservationRejected('slot must be a nonnegative integer')
    validate_reading(pulses)
    if not isinstance(calibration, CalibrationRevision) or calibration.instrument != instrument:
        raise ObservationRejected('the specified calibration revision is unavailable for this instrument')
