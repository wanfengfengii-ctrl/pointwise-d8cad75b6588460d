import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from capture.calibration import register_calibration
from capture.ingest import record
from dispatch.request_ids import RequestIdentity
from dispatch.retry import TransferInterrupted
from station_store import Archives
from tally.current import current


def stop_at(target):
    def checkpoint(stage):
        if stage == target:
            raise TransferInterrupted(stage)
    return checkpoint


def emit(case_id, inputs, expected, actual, downstream_expected, downstream_actual, paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': paths, 'oracle': oracle,
    }, sort_keys=True), flush=True)


class ArchiveCase(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory(prefix='chengwan-test-'))
        self.root = Path(folder)
        self.paths = self.root / 'east.sqlite', self.root / 'west.sqlite'
        self.reopen()
        for station in ('west', 'east'):
            self.archives.initialize_station(station)
            register_calibration(self.archives, station, 'meter-a', 'half', 1, 2)

    def reopen(self):
        self.archives = Archives(*self.paths)

    def capture(self, slot=1, pulses=34, *, station='east', shift='morning', recording='m', revision='half'):
        return record(self.archives, station, shift, recording, 'meter-a', slot, revision, pulses)

    def outward(self, observation, number='outward'):
        return RequestIdentity(number, observation.record_id, 'east', 'west', observation.episode)

    def returning(self, receipt, number='return'):
        return RequestIdentity(number, receipt.identity.record_id, 'west', 'east', receipt.episode)

    def check_custody(self, observation, expected, *, result=None):
        if result is None:
            result = current(self.archives, observation.origin.shift)
        lines = tuple(line for line in result.lines if line.record_id == observation.record_id)
        values = tuple(sum(line.millilitres for line in lines if line.station == station)
                       for station in ('east', 'west'))
        marker = 'CUSTODY_DUPLICATE' if len(lines) > 1 else 'CUSTODY_MISMATCH'
        message = f'{marker} record=m east={values[0]} west={values[1]}'
        self.assertEqual(values, expected, message)
        self.assertEqual(len(lines), 1, message)
        self.assertEqual(lines[0].observation, observation)
        return lines[0], [str(value) for value in values]

    def issued_ids(self, station='east'):
        with self.archives.open(station) as db:
            sheets = [row[0] for row in db.execute('SELECT sheet_id FROM shift_sheets ORDER BY sheet_id')]
            receipts = [row[0] for row in db.execute('SELECT receipt_id FROM shift_issue_receipts ORDER BY receipt_id')]
        return [sheets, receipts]
