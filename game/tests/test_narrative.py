"""Pure narrative and schema checks; temporary files never touch local slots."""
from copy import deepcopy
import unittest
from game.items.inventory import Inventory
from game.levels.haunted_house import load_level
from game.systems.narrative import (STORY, DOCUMENT_IDS, CORE_EVIDENCE, EVENT_IDS,
                                     NarrativeProgress, truth_eligible, event_ready, validate_narrative)
from game.systems.save_manager import validate_save, SaveError
from game.tests.test_save import base_save


class NarrativeTests(unittest.TestCase):
    def setUp(self):
        self.level = load_level()
        self.inventory = Inventory(self.level.items)
        self.progress = NarrativeProgress(self.inventory)

    def test_eight_short_unique_records_use_existing_level_authority(self):
        self.assertEqual(len(DOCUMENT_IDS),8)
        for item_id in DOCUMENT_IDS:
            entry = self.level.items[item_id]
            self.assertTrue(entry['lore'] and entry['unique'])
            self.assertLess(len(entry['text'].split()),100)
            spawns = [p for p in self.level.spawns['pickups'] if p['item']==item_id]
            self.assertEqual(len(spawns),1)
            self.assertNotIn('requires',spawns[0])

    def test_evidence_collection_is_unique_and_cannot_be_consumed(self):
        item = next(iter(DOCUMENT_IDS))
        self.assertTrue(self.inventory.add(item))
        self.assertFalse(self.inventory.add(item))
        self.assertFalse(self.inventory.consume(item))
        self.assertEqual(self.progress.documents,(item,))

    def test_normal_ending_needs_key_and_never_optional_evidence(self):
        self.assertEqual(self.progress.endings,())
        self.inventory.add_key('exit_key')
        self.assertEqual(self.progress.endings,('escape',))

    def test_truth_requires_three_core_records_and_at_least_five_total(self):
        self.assertFalse(truth_eligible(CORE_EVIDENCE))
        extras = sorted(DOCUMENT_IDS-CORE_EVIDENCE)
        self.assertFalse(truth_eligible(CORE_EVIDENCE|{extras[0]}))
        self.assertTrue(truth_eligible(CORE_EVIDENCE|set(extras[:2])))
        self.assertFalse(truth_eligible(DOCUMENT_IDS-{'lore_keeper_confession'}))
        for item in CORE_EVIDENCE|set(extras[:2]): self.inventory.add(item)
        self.inventory.add_key('exit_key')
        self.assertEqual(self.progress.endings,('escape','truth'))
        self.assertEqual(self.progress.discoveries,set(CORE_EVIDENCE))

    def test_authored_trigger_rules_do_not_bypass_puzzles(self):
        flags = dict(power_restored=False,safe_unlocked=False,boards_removed=False)
        self.assertFalse(event_ready('power_restoration',{},flags))
        self.assertTrue(event_ready('first_warning',{'household_order':1},flags))
        self.assertTrue(event_ready('the_watcher',{'lore_keeper_journal':1},flags))
        self.assertFalse(event_ready('bedroom_memory',{},flags,True))
        flags['power_restored']=flags['safe_unlocked']=True
        self.assertTrue(event_ready('bedroom_memory',{},flags,True))
        self.assertFalse(event_ready('bedroom_memory',{},flags,False))
        self.assertFalse(event_ready('missing',{},flags,True,True))

    def test_final_warning_requires_evidence_key_and_exit_proximity(self):
        inventory = {item:1 for item in DOCUMENT_IDS}
        self.assertFalse(event_ready('final_warning',inventory,{},True,True))
        inventory['exit_key']=1
        self.assertFalse(event_ready('final_warning',inventory,{},True,False))
        self.assertTrue(event_ready('final_warning',inventory,{},True,True))

    def test_schema_one_legacy_snapshot_migrates_without_mutating_input(self):
        old = base_save()
        before = deepcopy(old)
        data = validate_save(old)
        self.assertEqual(old,before)
        self.assertEqual(data['version'],1)
        self.assertEqual(data['narrative'],dict(version=1,documents=[],events=[],intro_seen=True))

    def test_lore_save_world_inventory_and_narrative_must_agree(self):
        data = base_save()
        data['inventory']={'lore_family_photo':1}
        data['world']['collected']=['story_family_photo']
        migrated = validate_save(data)
        self.assertEqual(migrated['narrative']['documents'],['lore_family_photo'])
        migrated['narrative']['documents']=[]
        with self.assertRaises(SaveError):validate_save(migrated)

    def test_invalid_narrative_types_unknown_duplicate_ids_and_gates_rejected(self):
        valid = validate_save(base_save())
        for key,value in (('version',True),('version',2),('intro_seen',1),('documents',['unknown']),
                          ('events',['unknown']),('events',['first_warning','first_warning']),
                          ('events',['power_restoration']),('documents',{})):
            data = deepcopy(valid);data['narrative'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(SaveError):validate_save(data)
        data=deepcopy(valid);data['narrative']=None
        with self.assertRaises(SaveError):validate_save(data)

    def test_snapshot_roundtrip_resets_transients_and_retains_events(self):
        self.inventory.add('lore_keeper_journal')
        self.progress.completed_events.add('the_watcher')
        self.progress.intro_seen=True
        snapshot = validate_narrative(self.progress.snapshot(),self.inventory.quantities,{})
        restored = NarrativeProgress(self.inventory);restored.restore(snapshot)
        self.assertEqual(restored.snapshot(),snapshot)
        self.assertFalse(restored.mystery_uncovered)
        self.assertNotIn('active',snapshot)

    def test_cards_have_brief_readable_duration_and_exactly_two_endings(self):
        self.assertEqual(set(STORY['endings']),{'escape','truth'})
        for cards in (STORY['intro'],*STORY['endings'].values()):
            self.assertTrue(20 <= len(cards)*7 <= 35)
            self.assertTrue(all(len(card['text'].split()) <= 50 for card in cards))

    def test_scripted_event_catalog_has_stable_unique_ids_and_bounded_durations(self):
        self.assertEqual(len(EVENT_IDS),6)
        self.assertEqual(len(STORY['events']),6)
        for event in STORY['events']:
            self.assertTrue(3 <= event['seconds'] <= 6)
            self.assertTrue(event['caption'])


if __name__=='__main__':unittest.main()
