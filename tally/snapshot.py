from dataclasses import dataclass
import sqlite3

from capture.recordings import OriginFact, list_origin_facts, read_origin_version
from dispatch.custody import OutgoingFact, list_outgoing_facts, read_outgoing_version
from receive.custody import IncomingDecision, list_incoming_facts, read_incoming_version
from receive.evidence import InboxFact, list_inbox_facts, read_evidence_version
from station_store import STATIONS, atomic


class CustodyUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class StationFacts:
    station: str
    origins: tuple[OriginFact, ...]
    outgoing: tuple[OutgoingFact, ...]
    inbox: tuple[InboxFact, ...]
    incoming: tuple[IncomingDecision, ...]


def _versions(archives):
    versions = []
    for station in STATIONS:
        with archives.open(station) as db, atomic(db, write=False):
            versions.append((read_origin_version(db), read_outgoing_version(db),
                             read_evidence_version(db), read_incoming_version(db)))
    return tuple(versions)


def _read_station(archives, station, shift, before_read):
    if before_read is not None:
        before_read(station, 'facts')
    with archives.open(station) as db, atomic(db, write=False):
        origins = list_origin_facts(db, shift)
        outgoing = list_outgoing_facts(db)
        inbox = list_inbox_facts(db)
        if before_read is not None:
            before_read(station, 'decisions')
        return StationFacts(station, origins, outgoing, inbox, list_incoming_facts(db))


def read_coherent_view(archives, shift, *, before_read=None, attempts=3):
    if type(attempts) is not int or attempts < 1:
        raise ValueError('attempts must be a positive integer')
    try:
        for _ in range(attempts):
            before = _versions(archives)
            facts = tuple(_read_station(archives, station, shift, before_read) for station in STATIONS)
            after = _versions(archives)
            if before == after:
                return facts
    except (OSError, sqlite3.Error) as error:
        raise CustodyUnavailable('a station custody fact could not be read') from error
    raise CustodyUnavailable('custody facts changed during the read')
