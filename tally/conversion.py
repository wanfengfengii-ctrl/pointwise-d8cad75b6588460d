from dataclasses import dataclass
from fractions import Fraction

from capture.observation import Observation


@dataclass(frozen=True)
class QuantityLine:
    station: str
    episode: str
    observation: Observation
    millilitres: Fraction | None

    @property
    def record_id(self):
        return self.observation.record_id

    @property
    def origin(self):
        return self.observation.origin


def convert_observation(station, episode, observation):
    pulses = observation.pulses
    quantity = None if pulses is None else pulses * observation.calibration.millilitres_per_pulse
    return QuantityLine(station, episode, observation, quantity)
