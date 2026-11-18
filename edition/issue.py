from edition.documents import freeze_shift
from edition.storage import commit_issue


def issue(archives, station, sheet_id, result, *, before_commit=None):
    tally = result() if callable(result) else result
    sheet, receipt = freeze_shift(station, sheet_id, tally)
    return commit_issue(archives, sheet, receipt, before_commit=before_commit)
