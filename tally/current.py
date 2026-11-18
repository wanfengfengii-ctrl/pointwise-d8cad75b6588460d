from station_store import require_text
from tally.aggregation import aggregate_shift
from tally.conversion import convert_observation
from tally.selection import select_current_episodes
from tally.snapshot import read_coherent_view


def current(archives, shift, *, before_read=None, attempts=3):
    require_text(shift, 'shift')
    view = read_coherent_view(archives, shift, before_read=before_read, attempts=attempts)
    lines = (convert_observation(episode.station, episode.episode, episode.observation)
             for episode in select_current_episodes(view, shift))
    return aggregate_shift(shift, lines)
