from edition.documents import encode_sheet
from edition.read import read_sheet


def export_sheet(archives, station, sheet_id):
    return encode_sheet(read_sheet(archives, station, sheet_id))
