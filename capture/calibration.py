from dataclasses import dataclass
from fractions import Fraction

from station_store import atomic, require_text


@dataclass(frozen=True)
class CalibrationRevision:
    instrument: str
    revision: str
    millilitres_per_pulse: Fraction

    def __post_init__(self):
        require_text(self.instrument, 'instrument')
        require_text(self.revision, 'revision')
        if not isinstance(self.millilitres_per_pulse, Fraction) or self.millilitres_per_pulse <= 0:
            raise ValueError('calibration requires a positive rational multiplier')

    def to_data(self):
        rate = self.millilitres_per_pulse
        return [self.instrument, self.revision, rate.numerator, rate.denominator]

    @classmethod
    def from_data(cls, data):
        instrument, revision, numerator, denominator = data
        return cls(instrument, revision, Fraction(numerator, denominator))


def initialize_calibrations(db):
    db.execute('''CREATE TABLE IF NOT EXISTS calibrations (
        instrument TEXT NOT NULL, revision TEXT NOT NULL,
        numerator TEXT NOT NULL, denominator TEXT NOT NULL,
        PRIMARY KEY (instrument, revision))''')


def load_calibration(db, instrument, revision):
    row = db.execute('''SELECT numerator, denominator FROM calibrations
                        WHERE instrument = ? AND revision = ?''', (instrument, revision)).fetchone()
    if row is None:
        return None
    numerator, denominator = map(int, row)
    return CalibrationRevision(instrument, revision, Fraction(numerator, denominator))


def register_calibration(archives, station, instrument, revision, numerator, denominator):
    if type(numerator) is not int or type(denominator) is not int or numerator <= 0 or denominator <= 0:
        raise ValueError('calibration numerator and denominator must be positive integers')
    calibration = CalibrationRevision(instrument, revision, Fraction(numerator, denominator))
    with archives.open(station) as db, atomic(db):
        previous = load_calibration(db, instrument, revision)
        if previous is None:
            rate = calibration.millilitres_per_pulse
            db.execute('INSERT INTO calibrations VALUES (?, ?, ?, ?)',
                       (instrument, revision, str(rate.numerator), str(rate.denominator)))
        elif previous != calibration:
            raise ValueError('a registered calibration revision is immutable')
    return calibration
