import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from capture.calibration import register_calibration
from capture.ingest import record
from dispatch.request import transfer_request
from dispatch.request_ids import RequestIdentity
from dispatch.retire import retire
from dispatch.retry import TransferInterrupted, apply_transfer_result
from edition.export import export_sheet
from edition.issue import issue
from receive.receipts import take_receipt
from station_store import Archives
from tally.current import current


def _sample(name):
    return json.loads((Path(__file__).resolve().parent / 'samples' / name).read_text(encoding='utf-8'))


def _station_quantities(result):
    return {part.station: {'millilitres': str(part.millilitres), 'missing': part.missing,
                           'records': [line.record_id for line in part.lines]}
            for part in result.stations}


def demo():
    morning = _sample('morning.json')
    movement = _sample('transfer.json')
    source, destination, shift = movement['source'], movement['destination'], morning['shift']
    with TemporaryDirectory(prefix='chengwan-') as directory:
        paths = (Path(directory) / 'east.sqlite', Path(directory) / 'west.sqlite')
        archives = Archives(*paths)
        archives.initialize()
        station, instrument, revision = morning['station'], morning['instrument'], morning['revision']
        register_calibration(archives, station, instrument, revision, morning['numerator'], morning['denominator'])
        observations = {slot: record(archives, station, shift, morning['recording'], instrument, slot, revision, pulses)
                        for slot, pulses in morning['observations']}
        original = observations[movement['slot']]
        before = current(archives, shift)
        signed = issue(archives, source, morning['sheet_id'], before)
        historical = export_sheet(archives, source, signed.sheet_id)
        outward = RequestIdentity(movement['first_request'], original.record_id, source, destination, original.episode)

        def interrupt(stage):
            if stage == movement['interrupt_at']:
                raise TransferInterrupted(stage)

        try:
            transfer_request(archives, outward, checkpoint=interrupt)
        except TransferInterrupted as error:
            missed_reply = str(error)
        else:
            raise RuntimeError('the transfer interruption did not occur')
        archives = Archives(*paths)
        after_loss = current(archives, shift)
        if (after_loss.at(source).millilitres, after_loss.at(destination).millilitres, after_loss.missing) != (0, 17, 1):
            raise RuntimeError('incorrect station quantities after interruption')
        first = transfer_request(archives, outward)
        retire(archives, source, outward.episode, first.receipt_id)
        collected = take_receipt(archives, destination, first.receipt_id)
        if collected != first or collected.observation != original:
            raise RuntimeError('destination receipt did not deliver the complete original')
        returning = RequestIdentity(movement['return_request'], original.record_id, destination, source, first.episode)
        returned = transfer_request(archives, returning)
        apply_transfer_result(archives, first)
        replay = transfer_request(archives, outward)
        final = current(archives, shift)
        fixed = export_sheet(archives, source, signed.sheet_id)
        if replay != first or fixed != historical or (final.at(source).millilitres, final.at(destination).millilitres) != (17, 0):
            raise RuntimeError('return or historical replay changed the wrong archival record')
        print(json.dumps({
            'before': _station_quantities(before), 'after_lost_reply': _station_quantities(after_loss),
            'interruption': missed_reply, 'receipt': collected.receipt_id, 'delivered': collected.observation.to_data(),
            'returned_receipt': returned.receipt_id, 'replayed_receipt': replay.receipt_id,
            'after_return': _station_quantities(final), 'fixed_sheet': json.loads(fixed),
        }, ensure_ascii=False, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description='Run the observation archive demonstration')
    parser.add_argument('action', choices=('demo',))
    parser.parse_args()
    demo()


if __name__ == '__main__':
    main()
