from fractions import Fraction

from capture.calibration import load_calibration, register_calibration
from capture.recordings import load_observation
from capture.validation import ObservationRejected
from dispatch.request import transfer_request
from dispatch.request_ids import TransferRejected
from dispatch.retire import retire
from edition.export import export_sheet
from edition.issue import issue
from edition.read import SheetNotFound, read_sheet
from edition.storage import SheetConflict
from receive.receipts import take_receipt
from tally.current import current
from tests.support import ArchiveCase, emit


class ReviewTests(ArchiveCase):
    def test_reopen_and_retire(self):
        observation = self.capture()
        request = self.outward(observation)
        old = issue(self.archives, 'east', 'before', current(self.archives, 'morning'))
        fixed_text = export_sheet(self.archives, 'east', old.sheet_id)
        receipt = transfer_request(self.archives, request)
        retire(self.archives, 'east', request.episode, receipt.receipt_id)
        self.reopen()
        self.archives.initialize()
        with self.archives.open('east') as db:
            self.assertIsNone(load_observation(db, observation.record_id, observation.episode))
        with self.assertRaises(ObservationRejected):
            self.capture()
        parked = self.root / 'parked.sqlite'
        self.paths[0].rename(parked)
        try:
            collected = take_receipt(self.archives, 'west', receipt.receipt_id)
            self.assertEqual(collected, receipt)
        finally:
            parked.rename(self.paths[0])
        sheet = read_sheet(self.archives, 'east', old.sheet_id)
        self.assertEqual(sheet.tally.millilitres, 17)
        self.assertEqual(sheet.tally.lines[0].observation, observation)
        self.assertEqual(sheet.tally.lines[0].station, 'east')
        after = export_sheet(self.archives, 'east', old.sheet_id)
        self.assertEqual(after, fixed_text)
        _, quantities = self.check_custody(observation, (0, 17))
        emit('v7', {'retire_source': True, 'receipt_read_with_source_file_absent': True},
             {'pulses': 34, 'current': ['0', '17']}, {'pulses': collected.observation.pulses, 'current': quantities},
             True, after == fixed_text, ['dispatch/retire.py', 'receive/receipts.py', 'edition/read.py', 'edition/export.py'],
             'Receipt uses the destination archive and the old sheet keeps its fixed east-station calculation.')

    def test_retire_after_return(self):
        observation = self.capture()
        old = issue(self.archives, 'east', 'before-return', current(self.archives, 'morning'))
        fixed_text = export_sheet(self.archives, 'east', old.sheet_id)
        outward = transfer_request(self.archives, self.outward(observation))
        returned = transfer_request(self.archives, self.returning(outward))
        with self.assertRaises(TransferRejected):
            retire(self.archives, 'east', returned.episode, outward.receipt_id)
        self.check_custody(observation, (17, 0))
        retire(self.archives, 'east', observation.episode, outward.receipt_id)
        retire(self.archives, 'east', observation.episode, outward.receipt_id)
        retire(self.archives, 'west', outward.episode, returned.receipt_id)
        self.reopen()
        line, quantities = self.check_custody(observation, (17, 0))
        self.assertEqual(line.episode, returned.episode)
        historical = take_receipt(self.archives, 'west', outward.receipt_id)
        newest = take_receipt(self.archives, 'east', returned.receipt_id)
        self.assertEqual(historical, outward)
        self.assertEqual(newest, returned)
        still_fixed = export_sheet(self.archives, 'east', old.sheet_id) == fixed_text
        self.assertTrue(still_fixed)
        emit('v7.retire_after_return', {'old_episode': observation.episode, 'return_episode': returned.episode},
             ['17', '0'], quantities, {'history': True, 'current_receipt': True, 'fixed_sheet': True},
             {'history': historical == outward, 'current_receipt': newest == returned, 'fixed_sheet': still_fixed},
             ['dispatch/retire.py', 'capture/recordings.py', 'receive/evidence.py', 'receive/receipts.py', 'edition/export.py'],
             'Retiring two ended episodes cannot touch the third episode or erase their archival indexes.')

    def test_reinitialize_user_data(self):
        original = self.capture()
        expected_calibration = register_calibration(self.archives, 'east', 'meter-a', 'spare', 2, 3)
        another = self.capture(8, 2, shift='later', recording='user', revision='spare')
        old = issue(self.archives, 'east', 'user-sheet', current(self.archives, 'later'))
        fixed_text = export_sheet(self.archives, 'east', old.sheet_id)
        request = self.outward(original)
        receipt = transfer_request(self.archives, request)
        self.reopen()
        self.archives.initialize()
        self.archives.initialize()
        with self.archives.open('east') as db:
            stored_calibration = load_calibration(db, 'meter-a', 'spare')
        self.assertEqual(stored_calibration, expected_calibration)
        later = current(self.archives, 'later')
        self.assertEqual(later.lines[0].observation, another)
        self.assertEqual(later.millilitres, Fraction(4, 3))
        self.assertEqual(transfer_request(self.archives, request), receipt)
        collected = take_receipt(self.archives, 'west', receipt.receipt_id)
        self.assertEqual(collected, receipt)
        self.assertEqual(issue(self.archives, 'east', old.sheet_id, later), old)
        after = export_sheet(self.archives, 'east', old.sheet_id)
        self.assertEqual(after, fixed_text)
        emit('v7.reinitialize_user_data', {'initializations': 2, 'pulses': 2, 'rate': [2, 3]},
             {'millilitres': '4/3', 'slot': 8}, {'millilitres': str(later.millilitres), 'slot': later.lines[0].origin.slot},
             {'receipt': True, 'sheet': True}, {'receipt': collected == receipt, 'sheet': after == fixed_text},
             ['station_store.py', 'capture/calibration.py', 'capture/recordings.py', 'receive/receipts.py', 'edition/storage.py'],
             'User-created data persists across initialization, including the independent exact 2 * 2/3 calculation.')

    def test_issue_rollback(self):
        self.capture()
        result = current(self.archives, 'morning')
        old = issue(self.archives, 'east', 'old', result)
        fixed = export_sheet(self.archives, 'east', old.sheet_id)
        self.capture(2, 2)
        updated = current(self.archives, 'morning')
        self.assertEqual(updated.millilitres, 18)

        def interrupt():
            raise RuntimeError('before sheet commit')

        with self.assertRaisesRegex(RuntimeError, 'before sheet commit') as error:
            issue(self.archives, 'east', 'failed', updated, before_commit=interrupt)
        self.reopen()
        self.assertEqual(export_sheet(self.archives, 'east', 'old'), fixed)
        with self.assertRaises(SheetNotFound):
            read_sheet(self.archives, 'east', 'failed')
        self.assertEqual(self.issued_ids(), [['old'], ['issue:east:old']])
        with self.assertRaises(SheetConflict):
            issue(self.archives, 'east', 'old', updated)
        self.assertEqual(read_sheet(self.archives, 'east', 'old').tally.millilitres, 17)
        emit('v8', {'old_millilitres': '17', 'new_millilitres': str(updated.millilitres), 'cut': 'before_commit'},
             'RuntimeError', type(error.exception).__name__, [['old'], ['issue:east:old']], self.issued_ids(),
             ['edition/issue.py', 'edition/storage.py', 'edition/read.py'],
             'The only persistent sheet and receipt IDs belong to the transaction that committed.')
