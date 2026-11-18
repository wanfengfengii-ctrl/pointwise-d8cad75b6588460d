from dataclasses import dataclass
from fractions import Fraction
import json

from capture.observation import Observation
from station_store import require_station, require_text
from tally.aggregation import ShiftTally, StationTotals
from tally.conversion import QuantityLine


@dataclass(frozen=True)
class ShiftSheet:
    sheet_id: str
    issuing_station: str
    tally: ShiftTally


@dataclass(frozen=True)
class IssueReceipt:
    receipt_id: str
    sheet_id: str
    station: str


def freeze_shift(station, sheet_id, tally):
    require_station(station)
    require_text(sheet_id, 'sheet ID')
    if not isinstance(tally, ShiftTally):
        raise TypeError('issue requires a successfully computed ShiftTally')
    return ShiftSheet(sheet_id, station, tally), IssueReceipt(f'issue:{station}:{sheet_id}', sheet_id, station)


def _pair(quantity):
    if quantity is None:
        return None
    return [quantity.numerator, quantity.denominator]


def _line_data(line):
    return {'episode': line.episode, 'observation': line.observation.to_data(),
            'millilitres': _pair(line.millilitres)}


def encode_sheet(sheet):
    result = sheet.tally
    data = {
        'version': 1,
        'sheet_id': sheet.sheet_id,
        'issuing_station': sheet.issuing_station,
        'shift': result.shift,
        'millilitres': _pair(result.millilitres),
        'missing': result.missing,
        'stations': [
            {'station': station.station, 'millilitres': _pair(station.millilitres), 'missing': station.missing,
             'lines': [_line_data(line) for line in station.lines]}
            for station in result.stations
        ],
    }
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def _decode_line(station, data):
    amount = data['millilitres']
    return QuantityLine(station, data['episode'], Observation.from_data(data['observation']),
                        None if amount is None else Fraction(*amount))


def decode_sheet(text):
    data = json.loads(text)
    if data['version'] != 1:
        raise ValueError('unsupported shift-sheet version')
    stations = []
    for item in data['stations']:
        station = item['station']
        lines = tuple(_decode_line(station, line) for line in item['lines'])
        stations.append(StationTotals(station, lines, Fraction(*item['millilitres']), item['missing']))
    result = ShiftTally(data['shift'], tuple(stations))
    if result.millilitres != Fraction(*data['millilitres']) or result.missing != data['missing']:
        raise ValueError('stored shift totals disagree with the station totals')
    return ShiftSheet(data['sheet_id'], data['issuing_station'], result)
