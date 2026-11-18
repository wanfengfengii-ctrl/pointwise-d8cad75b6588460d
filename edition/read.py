from edition.storage import load_sheet_bundle
from station_store import require_text


class SheetNotFound(LookupError):
    pass


def read_sheet(archives, station, sheet_id):
    require_text(sheet_id, 'sheet ID')
    with archives.open(station) as db:
        bundle = load_sheet_bundle(db, sheet_id)
    if bundle is None:
        raise SheetNotFound(sheet_id)
    return bundle[0]
