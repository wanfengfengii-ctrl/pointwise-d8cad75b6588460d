from dataclasses import dataclass
from hashlib import sha256
import json

from capture.calibration import CalibrationRevision
from station_store import require_station, require_text


def origin_episode(record_id):
    return 'origin:' + record_id


@dataclass(frozen=True, order=True)
class Origin:
    station: str
    shift: str
    recording: str
    instrument: str
    slot: int

    def __post_init__(self):
        require_station(self.station)
        require_text(self.shift, 'shift')
        require_text(self.recording, 'recording')
        require_text(self.instrument, 'instrument')
        if type(self.slot) is not int or self.slot < 0:
            raise ValueError('slot must be a nonnegative integer')

    def to_data(self):
        return [self.station, self.shift, self.recording, self.instrument, self.slot]

    @property
    def record_id(self):
        return json.dumps(self.to_data(), separators=(',', ':'))


@dataclass(frozen=True)
class Observation:
    origin: Origin
    calibration: CalibrationRevision
    pulses: int | None

    @property
    def record_id(self):
        return self.origin.record_id

    @property
    def episode(self):
        return origin_episode(self.record_id)

    def to_data(self):
        return {'origin': self.origin.to_data(), 'calibration': self.calibration.to_data(), 'pulses': self.pulses}

    @classmethod
    def from_data(cls, data):
        return cls(Origin(*data['origin']), CalibrationRevision.from_data(data['calibration']), data['pulses'])

    def encode(self):
        return json.dumps(self.to_data(), sort_keys=True, separators=(',', ':'))

    @classmethod
    def decode(cls, text):
        return cls.from_data(json.loads(text))

    def digest(self):
        return sha256(self.encode().encode('ascii')).hexdigest()
