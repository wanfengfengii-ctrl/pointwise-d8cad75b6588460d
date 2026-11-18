from edition.documents import IssueReceipt, decode_sheet, encode_sheet
from station_store import atomic


class SheetConflict(ValueError):
    pass


def initialize_editions(db):
    db.execute('''CREATE TABLE IF NOT EXISTS shift_sheets (
        sheet_id TEXT PRIMARY KEY, body TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS shift_issue_receipts (
        receipt_id TEXT PRIMARY KEY, sheet_id TEXT NOT NULL UNIQUE REFERENCES shift_sheets(sheet_id),
        station TEXT NOT NULL)''')


def commit_issue(archives, sheet, receipt, *, before_commit=None):
    encoded = encode_sheet(sheet)
    with archives.open(sheet.issuing_station) as db, atomic(db):
        existing = db.execute('SELECT body FROM shift_sheets WHERE sheet_id = ?', (sheet.sheet_id,)).fetchone()
        if existing is not None:
            bundle = load_sheet_bundle(db, sheet.sheet_id)
            if existing[0] != encoded or bundle is None or bundle[1] != receipt:
                raise SheetConflict('sheet ID already has a different committed issue')
            return bundle[1]
        db.execute('INSERT INTO shift_sheets VALUES (?, ?)', (sheet.sheet_id, encoded))
        db.execute('INSERT INTO shift_issue_receipts VALUES (?, ?, ?)', (receipt.receipt_id, receipt.sheet_id, receipt.station))
        if before_commit is not None:
            before_commit()
    return receipt


def load_sheet_bundle(db, sheet_id):
    row = db.execute('''SELECT s.body, r.receipt_id, r.station
                        FROM shift_sheets AS s JOIN shift_issue_receipts AS r USING (sheet_id)
                        WHERE s.sheet_id = ?''', (sheet_id,)).fetchone()
    if row is None:
        return None
    body, receipt_id, station = row
    return decode_sheet(body), IssueReceipt(receipt_id, sheet_id, station)
