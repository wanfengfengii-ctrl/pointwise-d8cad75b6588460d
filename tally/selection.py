from dataclasses import dataclass

from capture.observation import Observation
from dispatch.request_ids import TransferRejected
from receive.custody import admitted_episodes
from tally.snapshot import CustodyUnavailable


@dataclass(frozen=True)
class CurrentEpisode:
    station: str
    episode: str
    observation: Observation


def select_current_episodes(view, shift):
    try:
        ended = set()
        for facts in view:
            for outgoing in facts.outgoing:
                if outgoing.recorded_receipt is not None or outgoing.retired:
                    ended.add(outgoing.grant.identity.episode)
            for decision in facts.incoming:
                ended.add(decision.grant.identity.episode)
        for facts in view:
            received = [(decision, evidence) for decision, evidence in admitted_episodes(facts.inbox, facts.incoming)
                        if evidence.observation.origin.shift == shift]
            received_records = {evidence.observation.record_id for _, evidence in received}
            for origin in facts.origins:
                if origin.episode in ended or origin.origin.record_id in received_records:
                    continue
                if origin.observation is None:
                    raise CustodyUnavailable('current origin payload is unavailable')
                yield CurrentEpisode(facts.station, origin.episode, origin.observation)
            for decision, evidence in received:
                if decision.episode in ended:
                    continue
                if not evidence.active_link:
                    raise CustodyUnavailable('current received payload is unavailable')
                yield CurrentEpisode(facts.station, decision.episode, evidence.observation)
    except TransferRejected as error:
        raise CustodyUnavailable('incoming custody evidence is inconsistent') from error
