from fractions import Fraction
import json

from dispatch.request import transfer_request
from dispatch.retry import TransferInterrupted
from edition.export import export_sheet
from edition.issue import issue
from edition.read import SheetNotFound, read_sheet
from tally.current import current
from tally.snapshot import CustodyUnavailable
from tests.support import ArchiveCase, emit, stop_at


class ShiftTests(ArchiveCase):
    def test_exact_quantity(self):
        first = self.capture()
        zero = self.capture(2, 0)
        missing = self.capture(3, None)
        result = current(self.archives, 'morning')
        self.assertEqual([line.observation for line in result.lines], [first, zero, missing])
        self.assertEqual([line.millilitres for line in result.lines], [Fraction(17), Fraction(0), None])
        self.assertEqual((result.millilitres, result.missing), (Fraction(17), 1))
        self.assertEqual((result.at('west').millilitres, result.at('west').missing), (0, 0))
        receipt = issue(self.archives, 'east', 'morning-1', result)
        fixed = read_sheet(self.archives, 'east', receipt.sheet_id)
        self.assertEqual(fixed.tally, result)
        encoded = json.loads(export_sheet(self.archives, 'east', receipt.sheet_id))
        self.assertEqual(encoded['millilitres'], [17, 1])
        self.assertEqual(encoded['missing'], 1)
        report = {'millilitres': str(result.millilitres), 'missing': result.missing,
                  'slots': [line.origin.slot for line in result.lines]}
        emit('v1', {'pulses': [34, 0, None], 'rate': [1, 2]}, {'millilitres': '17', 'missing': 1, 'slots': [1, 2, 3]},
             report, {'millilitres': [17, 1], 'missing': 1},
             {'millilitres': encoded['millilitres'], 'missing': encoded['missing']},
             ['capture/ingest.py', 'tally/conversion.py', 'tally/aggregation.py', 'edition/issue.py', 'edition/export.py'],
             '34/2 plus zero is 17 ml, and the third position is one missing shot.')

    def test_fractional_rows(self):
        self.capture(2, 1)
        self.capture(1, 1)
        result = current(self.archives, 'morning')
        self.assertEqual([line.origin.slot for line in result.lines], [1, 2])
        self.assertEqual([line.millilitres for line in result.lines], [Fraction(1, 2), Fraction(1, 2)])
        self.assertEqual(result.millilitres, Fraction(1))
        issue(self.archives, 'west', 'halves', result)
        self.reopen()
        fixed = read_sheet(self.archives, 'west', 'halves').tally
        self.assertEqual(fixed, result)
        encoded = json.loads(export_sheet(self.archives, 'west', 'halves'))
        line_pairs = [line['millilitres'] for station in encoded['stations'] for line in station['lines']]
        self.assertEqual(line_pairs, [[1, 2], [1, 2]])
        self.assertEqual(encoded['millilitres'], [1, 1])
        emit('v1.fractional_rows', {'pulses': [1, 1], 'rate': [1, 2]}, ['1/2', '1/2'],
             [str(line.millilitres) for line in result.lines], {'total': [1, 1], 'lines': [[1, 2], [1, 2]]},
             {'total': encoded['millilitres'], 'lines': line_pairs},
             ['tally/conversion.py', 'tally/aggregation.py', 'edition/documents.py'], 'Two exact halves sum to one before and after issue.')

    def test_empty_shift(self):
        result = current(self.archives, 'empty')
        self.assertEqual([part.station for part in result.stations], ['east', 'west'])
        self.assertEqual((result.lines, result.millilitres, result.missing), ((), 0, 0))
        receipt = issue(self.archives, 'east', 'empty-sheet', result)
        self.assertEqual(read_sheet(self.archives, 'east', receipt.sheet_id).tally, result)

    def test_unavailable_custody(self):
        observation = self.capture()
        request = self.outward(observation)
        with self.assertRaises(TransferInterrupted):
            transfer_request(self.archives, request, checkpoint=stop_at('after_receipt'))

        def blocked(station, phase):
            if (station, phase) == ('west', 'decisions'):
                raise OSError('west decision port unavailable')

        with self.assertRaises(CustodyUnavailable) as error:
            current(self.archives, 'morning', before_read=blocked)
        with self.assertRaises(CustodyUnavailable):
            issue(self.archives, 'east', 'blocked', lambda: current(self.archives, 'morning', before_read=blocked))
        with self.assertRaises(SheetNotFound):
            read_sheet(self.archives, 'east', 'blocked')
        self.assertEqual(self.issued_ids(), [[], []])
        self.check_custody(observation, (17, 0))
        emit('v6', {'blocked_port': 'west decisions', 'isolated_receipt': True}, 'CustodyUnavailable',
             type(error.exception).__name__, [[], []], self.issued_ids(),
             ['tally/snapshot.py', 'tally/current.py', 'edition/issue.py', 'edition/storage.py'],
             'A failed decision read leaves neither a verified tally nor committed issue rows.')

    def test_inconsistent_view(self):
        observation = self.capture()
        request = self.outward(observation)
        mixed_read = []

        def advance(station, phase):
            if (station, phase) == ('west', 'facts') and not mixed_read:
                mixed_read.append(transfer_request(self.archives, request))

        with self.assertRaises(CustodyUnavailable) as error:
            issue(self.archives, 'east', 'mixed', lambda: current(self.archives, 'morning', before_read=advance, attempts=1))
        self.assertEqual(len(mixed_read), 1)
        self.assertEqual(self.issued_ids(), [[], []])
        line, quantities = self.check_custody(observation, (0, 17))
        self.assertEqual(line.episode, mixed_read[0].episode)

        moves = []

        def advance_return(station, phase):
            if (station, phase) == ('west', 'facts') and not moves:
                moves.append(transfer_request(self.archives, self.returning(mixed_read[0])))

        stable = current(self.archives, 'morning', before_read=advance_return)
        line, final = self.check_custody(observation, (17, 0), result=stable)
        self.assertEqual(line.episode, moves[0].episode)
        signed = issue(self.archives, 'east', 'stable', stable)
        self.assertEqual(read_sheet(self.archives, 'east', signed.sheet_id).tally, stable)
        self.assertEqual(self.issued_ids(), [['stable'], ['issue:east:stable']])
        emit('v6.inconsistent_view', {'cut': 'between east and west fact reads', 'attempts_first': 1},
             {'first': 'CustodyUnavailable', 'west_after': ['0', '17'], 'east_after_return': ['17', '0']},
             {'first': type(error.exception).__name__, 'west_after': quantities, 'east_after_return': final},
             [['stable'], ['issue:east:stable']], self.issued_ids(),
             ['tally/snapshot.py', 'tally/selection.py', 'edition/issue.py'],
             'A transition between reads invalidates the combined interval, and a fresh interval follows the committed owner.')
