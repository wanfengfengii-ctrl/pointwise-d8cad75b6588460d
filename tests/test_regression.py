import json

from dispatch.request import transfer_request
from dispatch.retire import retire
from dispatch.retry import TransferInterrupted, apply_transfer_result
from edition.export import export_sheet
from edition.issue import issue
from receive.receipts import take_receipt
from tally.current import current
from tests.support import ArchiveCase, stop_at


class IncidentRegressionTests(ArchiveCase):
    """Regression coverage for the lost-reply double count in INCIDENT.md."""

    def test_lost_reply_counts_once_and_fixed_sheet_is_stable(self):
        observation = self.capture()
        self.capture(2, 0)
        self.capture(3, None)
        signed = issue(self.archives, 'east', 'morning-fixed', current(self.archives, 'morning'))
        fixed_text = export_sheet(self.archives, 'east', signed.sheet_id)

        request = self.outward(observation)
        with self.assertRaises(TransferInterrupted):
            transfer_request(self.archives, request, checkpoint=stop_at('before_reply'))
        self.reopen()

        # The reply was lost after the decision committed: the destination alone counts.
        line, quantities = self.check_custody(observation, (0, 17))
        self.assertEqual(line.episode, 'incoming:outward')
        self.assertEqual(quantities, ['0', '17'])

        # Replaying the original request settles the source book without a second count.
        first = transfer_request(self.archives, request)
        self.assertEqual(take_receipt(self.archives, 'west', first.receipt_id), first)
        self.check_custody(observation, (0, 17))

        # The sheet signed before the transfer still reads back its original figures.
        fixed = json.loads(export_sheet(self.archives, 'east', signed.sheet_id))
        self.assertEqual((fixed['millilitres'], fixed['missing']), ([17, 1], 1))
        east = fixed['stations'][0]
        self.assertEqual((east['station'], east['millilitres'], east['missing']), ('east', [17, 1], 1))
        self.assertEqual([line['observation']['origin'] for line in east['lines']],
                         [['east', 'morning', 'm', 'meter-a', slot] for slot in (1, 2, 3)])
        self.assertEqual([line['millilitres'] for line in east['lines']], [[17, 1], [0, 1], None])
        self.assertEqual(export_sheet(self.archives, 'east', signed.sheet_id), fixed_text)

    def test_return_then_replay_keeps_only_the_return_episode(self):
        observation = self.capture()
        request = self.outward(observation)
        with self.assertRaises(TransferInterrupted):
            transfer_request(self.archives, request, checkpoint=stop_at('before_reply'))
        original = take_receipt(self.archives, 'west', request.receipt_id)
        returned = transfer_request(self.archives, self.returning(original))
        self.assertEqual(apply_transfer_result(self.archives, original), original)

        # Replaying the first request collects its receipt without reviving the old episode.
        replay = transfer_request(self.archives, request)
        self.assertEqual(replay, original)
        self.reopen()
        line, quantities = self.check_custody(observation, (17, 0))
        self.assertEqual(line.episode, returned.episode)
        self.assertEqual(quantities, ['17', '0'])
        west_lines = [line for line in current(self.archives, 'morning').at('west').lines
                      if line.record_id == observation.record_id]
        self.assertEqual(west_lines, [])
        self.assertEqual(take_receipt(self.archives, 'west', original.receipt_id), original)

    def test_replay_after_source_retire_delivers_history(self):
        observation = self.capture()
        request = self.outward(observation)
        original = transfer_request(self.archives, request)
        retire(self.archives, 'east', request.episode, original.receipt_id)
        returned = transfer_request(self.archives, self.returning(original))
        self.reopen()

        # The retired source cannot re-deliver, yet the replay still returns the first receipt.
        self.assertEqual(transfer_request(self.archives, request), original)
        line, _ = self.check_custody(observation, (17, 0))
        self.assertEqual(line.episode, returned.episode)
