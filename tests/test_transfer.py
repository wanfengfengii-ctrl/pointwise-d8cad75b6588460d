from dataclasses import replace
from fractions import Fraction

from dispatch.request import transfer_request
from dispatch.request_ids import TransferRejected
from dispatch.retire import retire
from dispatch.retry import TransferInterrupted, apply_transfer_result
from receive.receipts import ReceiptNotFound, take_receipt
from tally.current import current
from tests.support import ArchiveCase, emit, stop_at


_MOVEMENT = ['dispatch/request.py', 'dispatch/custody.py', 'receive/custody.py', 'tally/selection.py']


class TransferTests(ArchiveCase):
    def test_regular_transfer(self):
        observation = self.capture()
        request = self.outward(observation)
        first = transfer_request(self.archives, request)
        line, quantities = self.check_custody(observation, (0, 17))
        self.assertEqual(line.episode, first.episode)
        self.assertEqual(line.station, 'west')
        self.assertEqual(line.millilitres, Fraction(17))
        self.assertNotEqual(first.episode, request.episode)
        replay = transfer_request(self.archives, request)
        collected = take_receipt(self.archives, 'west', first.receipt_id)
        self.assertEqual(first, replay)
        self.assertEqual(collected.observation, observation)
        self.assertEqual(collected.identity, request)
        with self.assertRaises(ReceiptNotFound):
            take_receipt(self.archives, 'east', first.receipt_id)
        emit('v3', {'pulses': 34, 'source': 'east', 'destination': 'west'}, ['0', '17'], quantities,
             {'same_receipt': True, 'pulses': 34}, {'same_receipt': replay == collected, 'pulses': collected.observation.pulses},
             _MOVEMENT + ['receive/receipts.py'], 'One 34-pulse original at the new station contributes 17 ml.')

    def test_pending_receipt(self):
        observation = self.capture()
        request = self.outward(observation)
        with self.assertRaisesRegex(TransferInterrupted, 'after_receipt'):
            transfer_request(self.archives, request, checkpoint=stop_at('after_receipt'))
        self.reopen()
        _, pending = self.check_custody(observation, (17, 0))
        with self.assertRaises(ReceiptNotFound) as missing:
            take_receipt(self.archives, 'west', request.receipt_id)
        with self.assertRaises(TransferRejected):
            retire(self.archives, 'east', request.episode, request.receipt_id)
        with self.assertRaises(TransferRejected):
            transfer_request(self.archives, replace(request, number='competing'))
        accepted = transfer_request(self.archives, request)
        _, settled = self.check_custody(observation, (0, 17))
        self.assertEqual(take_receipt(self.archives, 'west', accepted.receipt_id).observation, observation)
        emit('v3.pending_receipt', {'cut': 'after_receipt'}, ['17', '0'], pending,
             {'before': 'ReceiptNotFound', 'after': ['0', '17']},
             {'before': type(missing.exception).__name__, 'after': settled},
             _MOVEMENT + ['receive/evidence.py'], 'Only the committed decision authorizes the receiver and receipt.')

    def test_decision_rollback(self):
        observation = self.capture()
        request = self.outward(observation)
        with self.assertRaisesRegex(TransferInterrupted, 'before_decision_commit'):
            transfer_request(self.archives, request, checkpoint=stop_at('before_decision_commit'))
        self.reopen()
        self.check_custody(observation, (17, 0))
        with self.assertRaises(ReceiptNotFound):
            take_receipt(self.archives, 'west', request.receipt_id)
        receipt = transfer_request(self.archives, request)
        self.check_custody(observation, (0, 17))
        self.assertEqual(take_receipt(self.archives, 'west', receipt.receipt_id), receipt)

    def test_lost_reply_after_receipt(self):
        observation = self.capture()
        request = self.outward(observation)
        with self.assertRaisesRegex(TransferInterrupted, 'before_reply'):
            transfer_request(self.archives, request, checkpoint=stop_at('before_reply'))
        self.reopen()
        _, quantities = self.check_custody(observation, (0, 17))
        fixed = take_receipt(self.archives, 'west', request.receipt_id)
        self.assertEqual(fixed.observation, observation)
        replay = transfer_request(self.archives, request)
        self.assertEqual(fixed, replay)
        self.check_custody(observation, (0, 17))
        emit('v4', {'pulses': 34, 'cut': 'before_reply', 'reopen': True}, ['0', '17'], quantities,
             {'same_receipt': True, 'pulses': 34}, {'same_receipt': replay == fixed, 'pulses': fixed.observation.pulses},
             _MOVEMENT + ['dispatch/retry.py', 'tally/snapshot.py'], 'After destination commit, lost delivery cannot extend source custody.')

    def test_return_then_replay(self):
        observation = self.capture()
        request = self.outward(observation)
        with self.assertRaises(TransferInterrupted):
            transfer_request(self.archives, request, checkpoint=stop_at('before_reply'))
        original = take_receipt(self.archives, 'west', request.receipt_id)
        returned = transfer_request(self.archives, self.returning(original))
        self.assertNotEqual(returned.episode, observation.episode)
        self.reopen()
        line, _ = self.check_custody(observation, (17, 0))
        self.assertEqual(line.episode, returned.episode)
        self.assertEqual(apply_transfer_result(self.archives, original), original)
        self.check_custody(observation, (17, 0))
        replay = transfer_request(self.archives, request)
        self.assertEqual(replay, original)
        _, quantities = self.check_custody(observation, (17, 0))
        self.assertEqual(take_receipt(self.archives, 'west', original.receipt_id), original)
        with self.assertRaises(TransferRejected):
            apply_transfer_result(self.archives, replace(original, episode=returned.episode))
        self.assertEqual(current(self.archives, 'morning').lines[0].episode, returned.episode)
        emit('v5', {'sequence': ['outward', 'return', 'old-result', 'old-request']}, ['17', '0'], quantities,
             True, replay == original, _MOVEMENT + ['dispatch/retry.py'],
             'A historical response names the first episode, and the distinct return episode still owns the shot.')

    def test_changed_request(self):
        observation = self.capture()
        request = self.outward(observation)
        original = transfer_request(self.archives, request)
        returned = transfer_request(self.archives, self.returning(original))
        self.assertEqual(transfer_request(self.archives, request), original)
        with self.assertRaises(TransferRejected) as error:
            transfer_request(self.archives, replace(request, episode=returned.episode))
        line, quantities = self.check_custody(observation, (17, 0))
        old = take_receipt(self.archives, 'west', original.receipt_id)
        self.assertEqual(old, original)
        self.assertEqual(line.episode, returned.episode)
        emit('v5.changed_request', {'same_request': request.number, 'replaced_episode': returned.episode},
             'TransferRejected', type(error.exception).__name__, {'quantities': ['17', '0'], 'old_receipt': True},
             {'quantities': quantities, 'old_receipt': old == original}, _MOVEMENT + ['dispatch/request_ids.py'],
             'Request equality includes the source episode even when record and stations match.')
