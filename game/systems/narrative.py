"""Stable story data and persistent evidence; independent of rendering and AI."""
from copy import deepcopy
import json
from pathlib import Path

STORY = json.loads((Path(__file__).resolve().parents[1] / 'data/story.json').read_text(encoding='utf-8'))
DOCUMENT_IDS = frozenset(STORY['documents'])
EVENT_IDS = frozenset(event['id'] for event in STORY['events'])
CORE_EVIDENCE = frozenset(('lore_keeper_journal', 'lore_observation_log', 'lore_keeper_confession'))


def add_story_pickups(items, spawns):
    """Extend the existing level authority; never override mechanical items."""
    for item_id, entry in STORY['documents'].items():
        if item_id in items:
            raise ValueError('Story item conflicts with a mechanical item')
        items[item_id] = dict(type='note', lore=True, unique=True, name=entry['name'],
                              description='Optional evidence. Kept in the journal; Enter rereads.',
                              text=entry['text'], color=[162, 151, 126], scale=[.38, .035, .28])
        spawns['pickups'].append(dict(id='story_' + item_id.removeprefix('lore_'), item=item_id,
                                     **{key:deepcopy(entry[key]) for key in ('room','position','approach')}))


def event_ready(event_id, inventory, progression, near_boards=False, near_exit=False):
    return {
        'first_warning': bool(inventory.get('household_order')),
        'power_restoration': progression.get('power_restored', False),
        'the_watcher': bool(inventory.get('lore_keeper_journal')),
        'lockbox_revelation': progression.get('safe_unlocked', False),
        'bedroom_memory': progression.get('safe_unlocked', False) and near_boards,
        'final_warning': truth_eligible(inventory) and bool(inventory.get('exit_key')) and near_exit,
    }.get(event_id, False)


def truth_eligible(documents):
    found = set(documents) & DOCUMENT_IDS
    return len(found) >= 5 and CORE_EVIDENCE <= found


def validate_narrative(data, inventory, progression):
    found = sorted(set(inventory) & DOCUMENT_IDS)
    # Schema 1 snapshots without narrative fields migrate in memory only.
    if data is None:
        return dict(version=1, documents=found, events=[], intro_seen=True)
    if not isinstance(data, dict) or set(data) != {'version','documents','events','intro_seen'}:
        raise ValueError('Invalid narrative section')
    if type(data['version']) is not int or data['version'] != 1 or type(data['intro_seen']) is not bool:
        raise ValueError('Invalid narrative version or introduction state')
    for key, valid in (('documents',DOCUMENT_IDS),('events',EVENT_IDS)):
        ids = data[key]
        if (not isinstance(ids,list) or not all(isinstance(value,str) for value in ids)
                or len(ids) != len(set(ids)) or not set(ids) <= valid):
            raise ValueError('Invalid narrative IDs')
    if sorted(data['documents']) != found:
        raise ValueError('Evidence and inventory disagree')
    if any(not event_ready(e,inventory,progression,True,True) for e in data['events']):
        raise ValueError('Story event bypasses its prerequisites')
    return deepcopy(data)


class NarrativeProgress:
    def __init__(self, inventory):
        self.inventory = inventory
        self.completed_events = set()
        self.intro_seen = False

    @property
    def documents(self):
        return tuple(item for item in self.inventory.quantities if item in DOCUMENT_IDS)

    @property
    def discoveries(self):
        return set(self.documents) & CORE_EVIDENCE

    @property
    def mystery_uncovered(self):
        return truth_eligible(self.documents)

    @property
    def endings(self):
        if not self.inventory.has_key('exit_key'):
            return ()
        return ('escape','truth') if self.mystery_uncovered else ('escape',)

    def snapshot(self):
        return dict(version=1, documents=sorted(self.documents),
                    events=sorted(self.completed_events), intro_seen=self.intro_seen)

    def restore(self, data):
        self.completed_events = set(data['events'])
        self.intro_seen = data['intro_seen']
