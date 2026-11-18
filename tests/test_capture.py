from capture.calibration import register_calibration
from capture.validation import ObservationRejected
from tally.current import current
from tests.support import ArchiveCase, emit


class CaptureTests(ArchiveCase):
    def test_unknown_calibration(self):
        original = self.capture()
        with self.assertRaises(ObservationRejected) as error:
            self.capture(2, revision='unknown')
        result = current(self.archives, 'morning')
        self.assertEqual([line.observation for line in result.lines], [original])
        self.assertEqual(result.millilitres, 17)
        emit('v2', {'revision': 'unknown', 'slot': 2}, 'ObservationRejected', type(error.exception).__name__,
             {'slots': [1], 'millilitres': '17'},
             {'slots': [line.origin.slot for line in result.lines], 'millilitres': str(result.millilitres)},
             ['capture/calibration.py', 'capture/ingest.py', 'tally/current.py'], 'Only the original 34/2 shot can contribute.')

    def test_conflicting_slot(self):
        original = self.capture()
        self.assertEqual(self.capture(), original)
        with self.assertRaises(ObservationRejected) as error:
            self.capture(pulses=48)
        self.reopen()
        result = current(self.archives, 'morning')
        self.assertEqual([line.observation for line in result.lines], [original])
        emit('v2.conflicting_slot', {'slot': 1, 'first': 34, 'second': 48}, 'ObservationRejected',
             type(error.exception).__name__, [34], [line.observation.pulses for line in result.lines],
             ['capture/ingest.py', 'capture/recordings.py'], 'First write fixes the shot at that position.')

    def test_bad_readings_and_fixed_revision(self):
        register_calibration(self.archives, 'east', 'meter-a', 'half', 2, 4)
        with self.assertRaises(ValueError):
            register_calibration(self.archives, 'east', 'meter-a', 'half', 2, 3)
        for invalid in (True, -1, 1.5, '34'):
            with self.subTest(invalid=invalid), self.assertRaises(ObservationRejected):
                self.capture(pulses=invalid)
        register_calibration(self.archives, 'east', 'other-meter', 'other', 1, 3)
        with self.assertRaises(ObservationRejected):
            self.capture(revision='other')
        with self.assertRaises(ObservationRejected):
            self.capture(slot=-1)
        self.assertEqual(current(self.archives, 'morning').lines, ())
        original = self.capture()
        register_calibration(self.archives, 'east', 'meter-a', 'next', 4, 1)
        self.assertEqual(current(self.archives, 'morning').lines[0].observation, original)
        self.assertEqual(current(self.archives, 'morning').millilitres, 17)
