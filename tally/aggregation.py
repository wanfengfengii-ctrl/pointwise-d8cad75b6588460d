from dataclasses import dataclass
from fractions import Fraction

from station_store import STATIONS, require_station
from tally.conversion import QuantityLine


@dataclass(frozen=True)
class StationTotals:
    station: str
    lines: tuple[QuantityLine, ...]
    millilitres: Fraction
    missing: int


@dataclass(frozen=True)
class ShiftTally:
    shift: str
    stations: tuple[StationTotals, ...]

    def at(self, station):
        require_station(station)
        return next(totals for totals in self.stations if totals.station == station)

    @property
    def lines(self):
        return tuple(line for station in self.stations for line in station.lines)

    @property
    def millilitres(self):
        return sum((station.millilitres for station in self.stations), Fraction(0))

    @property
    def missing(self):
        return sum(station.missing for station in self.stations)


def aggregate_shift(shift, lines):
    grouped = {station: [] for station in STATIONS}
    for line in lines:
        grouped[line.station].append(line)
    stations = []
    for station in STATIONS:
        ordered = tuple(sorted(grouped[station], key=lambda line: (line.origin, line.episode)))
        present = [line.millilitres for line in ordered if line.millilitres is not None]
        stations.append(StationTotals(station, ordered, sum(present, Fraction(0)), len(ordered) - len(present)))
    return ShiftTally(shift, tuple(stations))
