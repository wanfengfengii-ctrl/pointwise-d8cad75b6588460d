from dispatch.request import transfer_request
from dispatch.retire import retire
from dispatch.retry import TransferInterrupted, apply_transfer_result
from receive.receipts import take_receipt
from tests.support import ArchiveCase


class IncidentTests(ArchiveCase):
    def test_replay_after_source_retired(self):
        observation = self.capture()
        outward = self.outward(observation)
        original = transfer_request(self.archives, outward)
        retire(self.archives, 'east', outward.episode, original.receipt_id)
        self.reopen()
        self.check_custody(observation, (0, 17))
        self.assertEqual(take_receipt(self.archives, 'west', original.receipt_id), original)

        returned = transfer_request(self.archives, self.returning(original))
        self.reopen()
        self.assertEqual(apply_transfer_result(self.archives, original), original)
        try:
            replayed = transfer_request(self.archives, outward)
        except TransferInterrupted as error:
            self.fail(f'CUSTODY_HISTORY_RETRY committed receipt unavailable after retirement ({error})')
        self.assertEqual(replayed, original)
        line, _ = self.check_custody(observation, (17, 0))
        self.assertEqual(line.episode, returned.episode)
