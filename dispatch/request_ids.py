from dataclasses import dataclass
import json

from station_store import require_station, require_text


class TransferRejected(ValueError):
    pass


@dataclass(frozen=True)
class RequestIdentity:
    number: str
    record_id: str
    source: str
    destination: str
    episode: str

    def __post_init__(self):
        try:
            require_text(self.number, 'request number')
            require_text(self.record_id, 'record ID')
            require_text(self.episode, 'episode')
            require_station(self.source)
            require_station(self.destination)
        except ValueError as error:
            raise TransferRejected(str(error)) from error
        if self.source == self.destination:
            raise TransferRejected('a transfer must cross stations')

    @property
    def incoming_episode(self):
        return 'incoming:' + self.number

    @property
    def receipt_id(self):
        return 'transfer:' + self.number

    def to_data(self):
        return [self.number, self.record_id, self.source, self.destination, self.episode]

    def encode(self):
        return json.dumps(self.to_data(), separators=(',', ':'))

    @classmethod
    def decode(cls, text):
        return cls(*json.loads(text))


def initialize_request_ids(db):
    db.execute('''CREATE TABLE IF NOT EXISTS request_numbers (
        number TEXT PRIMARY KEY, identity TEXT NOT NULL)''')


def find_request_identity(db, number):
    row = db.execute('SELECT identity FROM request_numbers WHERE number = ?', (number,)).fetchone()
    return None if row is None else RequestIdentity.decode(row[0])


def bind_request_number(db, identity):
    db.execute('INSERT INTO request_numbers VALUES (?, ?) ON CONFLICT(number) DO NOTHING',
               (identity.number, identity.encode()))
    if find_request_identity(db, identity.number) != identity:
        raise TransferRejected('request number is bound to different parameters')
    return identity
