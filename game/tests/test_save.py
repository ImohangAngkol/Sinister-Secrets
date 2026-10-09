"""Pure JSON/IO regressions; all files are isolated in temporary directories."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from game.systems.save_manager import SaveManager, SaveError, validate_save


def base_save():
    return dict(version=1,level='haunted_house_v1',slot='manual',session=uuid4().hex,
                timestamp=datetime.now(timezone.utc).isoformat(),
                player=dict(position=[0,0,-16],yaw=124,pitch=27,battery=65,stamina=100,flashlight_on=False),
                inventory={},progression=dict(power_restored=False,safe_unlocked=False,boards_removed=False),
                world=dict(collected=[],doors=dict(exit_door=False,basement_door=False)))


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.manager=SaveManager(self.folder.name)
        self.data=base_save()

    def test_serialization_roundtrip_and_optional_defaults(self):
        written=self.manager.save(self.data)
        self.assertEqual(self.manager.load(),written)
        self.assertEqual(written['player']['camera_rotation'],[0,0,0])
        self.assertFalse(written['player']['crouching'])
        self.assertNotIn('entities',written)
        self.assertNotIn('objective',written)  # Derived from inventory/puzzle flags.

    def test_atomic_write_preserves_valid_file_on_replace_failure(self):
        self.manager.save(self.data)
        before=self.manager.path('manual').read_bytes()
        changed=deepcopy(self.data)
        changed['player']['battery']=44
        with patch('game.systems.save_manager.os.replace',side_effect=PermissionError()),self.assertRaises(PermissionError):
            self.manager.save(changed)
        self.assertEqual(self.manager.path('manual').read_bytes(),before)
        self.assertFalse(self.manager.path('manual').with_suffix('.json.tmp').exists())

    def test_missing_save_is_not_created_and_continue_unavailable(self):
        self.assertIsNone(self.manager.load())
        self.assertIsNone(self.manager.available())
        self.assertFalse(self.manager.exists())

    def test_corrupted_save_is_preserved_and_cannot_be_silently_replaced(self):
        path=self.manager.path('manual')
        for contents in ('{','[]','null','{"version":1,"version":1}','{"version":NaN}', '\ud800'):
            with self.subTest(contents=contents):
                path.write_bytes(contents.encode('utf-8',errors='surrogatepass'))
                before=path.read_bytes()
                self.assertIsNone(self.manager.load())
                self.assertTrue(self.manager.error)
                with self.assertRaises(SaveError):
                    self.manager.save(self.data)
                self.assertEqual(path.read_bytes(),before)

    def test_unsupported_versions_and_wrong_slots_are_rejected(self):
        for value in (0,2,True,'1'):
            data=deepcopy(self.data)
            data['version']=value
            with self.assertRaises(SaveError): validate_save(data)
        data=deepcopy(self.data)
        data['slot']='checkpoint'
        data['milestone']='power'
        self.manager.path('manual').write_text(json.dumps(data))
        self.assertIsNone(self.manager.load())
        with self.assertRaises(SaveError): self.manager.path('../outside')

    def test_invalid_critical_fields_are_rejected(self):
        cases=[('position',[0,0,19]),('position',[0,5,-15]),('position',[float('nan'),0,0]),
               ('position',[0,0]),('yaw',181),('pitch',-91),('battery',101),('battery',True),
               ('stamina',-1),('flashlight_on',1),('camera_rotation',[0,0,float('inf')]),
               ('camera_height',.5),('crouching',1),('regen_delay',9)]
        for key,value in cases:
            data=deepcopy(self.data);data['player'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(SaveError):validate_save(data)
        for key in ('inventory','progression','world','player','timestamp','session'):
            data=deepcopy(self.data);data.pop(key)
            with self.subTest(missing=key),self.assertRaises(SaveError):validate_save(data)

    def test_battery_and_stamina_bounds_accept_zero_and_maximum(self):
        for charge in (0,100):
            data=deepcopy(self.data)
            data['player'].update(battery=charge,stamina=0)
            self.assertTrue(validate_save(data)['player']['sprint_exhausted'])

    def test_inventory_cannot_duplicate_unknown_unique_or_uncollected_items(self):
        for inventory in ({'exit_key':2},{'unknown':1},{'flashlight':1},{'battery':1},{'fuse':True}):
            data=deepcopy(self.data);data['inventory']=inventory
            with self.subTest(inventory=inventory),self.assertRaises(SaveError):validate_save(data)

    def test_consistent_collected_and_consumed_battery_is_valid(self):
        data=deepcopy(self.data)
        data['world']['collected']=['kitchen_battery']
        self.assertEqual(validate_save(data)['inventory'],{})
        data['inventory']={'battery':1}
        self.assertEqual(validate_save(data)['inventory'],{'battery':1})
        data['inventory']['battery']=2
        with self.assertRaises(SaveError):validate_save(data)

    def test_puzzle_dependencies_consumed_fuse_and_crowbar_reward_are_validated(self):
        data=deepcopy(self.data)
        data['world']['collected']=['storage_fuse']
        data['progression']['power_restored']=True
        validate_save(data)
        data['progression']['safe_unlocked']=True
        with self.assertRaises(SaveError):validate_save(data)
        data['inventory']={'crowbar':1}
        validate_save(data)
        data['progression']['boards_removed']=True
        data['world']['collected'].append('bedroom_exit_key')
        data['inventory']['exit_key']=1
        validate_save(data)
        data['progression']['power_restored']=False
        with self.assertRaises(SaveError):validate_save(data)

    def test_doors_require_keys_and_basement_remains_sealed(self):
        for door in ('exit_door','basement_door'):
            data=deepcopy(self.data);data['world']['doors'][door]=True
            with self.assertRaises(SaveError):validate_save(data)

    def test_notes_must_match_collected_ids_and_remain_readable(self):
        data=deepcopy(self.data)
        data['world']['collected']=['living_instructions']
        data['inventory']={'household_order':1}
        self.assertEqual(validate_save(data)['inventory'],data['inventory'])
        data['world']['collected'].append('living_instructions')
        with self.assertRaises(SaveError):validate_save(data)

    def test_manual_continue_has_priority_over_checkpoint(self):
        checkpoint=deepcopy(self.data);checkpoint.update(slot='checkpoint',milestone='power')
        checkpoint['world']['collected']=['storage_fuse']
        checkpoint['progression']['power_restored']=True
        checkpoint['player']['position']=[0,0,-15]
        self.manager.save(checkpoint,'checkpoint')
        self.assertEqual(self.manager.available()[0],'checkpoint')
        self.manager.save(self.data)
        self.assertEqual(self.manager.available()[0],'manual')
        manual=self.manager.path('manual').read_bytes()
        self.manager.clear_checkpoint()
        self.assertEqual(self.manager.path('manual').read_bytes(),manual)

    def test_resource_state_never_serializes_an_impossible_on_flashlight(self):
        data=deepcopy(self.data);data['player']['flashlight_on']=True
        with self.assertRaises(SaveError):validate_save(data)

    def test_checkpoint_cannot_claim_incomplete_milestone_or_unsafe_respawn(self):
        data=deepcopy(self.data)
        data.update(slot='checkpoint',milestone='power')
        data['player']['position']=[0,0,-15]
        with self.assertRaises(SaveError):validate_save(data)
        data['world']['collected']=['storage_fuse']
        data['progression']['power_restored']=True
        validate_save(data)
        data['player']['position']=[0,0,-8]
        with self.assertRaises(SaveError):validate_save(data)

    def test_invalid_manual_falls_back_to_valid_checkpoint_without_overwriting(self):
        data=deepcopy(self.data)
        data.update(slot='checkpoint',milestone='power')
        data['player']['position']=[0,0,-15]
        data['world']['collected']=['storage_fuse']
        data['progression']['power_restored']=True
        self.manager.save(data,'checkpoint')
        self.manager.path('manual').write_text('{')
        self.assertEqual(self.manager.available()[0],'checkpoint')
        self.assertEqual(self.manager.path('manual').read_text(),'{')

    def test_save_size_limit_and_out_of_range_huge_integer_are_safe(self):
        self.manager.path('manual').write_text(' '*65537)
        self.assertIsNone(self.manager.load())
        data=deepcopy(self.data);data['player']['battery']=10**500
        with self.assertRaises(SaveError):validate_save(data)
