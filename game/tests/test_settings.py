"""Preferences tests use temporary JSON only; no game checkpoints or assets."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from game.settings import Preferences, PREFERENCE_DEFAULTS, validate_preferences, validate_bindings, BINDING_DEFAULTS


class SettingsTests(unittest.TestCase):
    def test_bindings_reject_conflicts_reserved_and_unsupported_keys(self):
        for action,key in (('forward','s'),('interact','escape'),('flashlight','enter'),
                           ('pause','backspace'),('forward','r'),('forward','f13')):
            values=dict(BINDING_DEFAULTS,**{action:key})
            with self.subTest(action=action,key=key),self.assertRaises(ValueError):validate_bindings(values)

    def test_rebound_controls_and_text_scale_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            prefs=Preferences(Path(folder)/'prefs.json')
            bindings=dict(BINDING_DEFAULTS,forward='i',pause='p')
            prefs.save(dict(PREFERENCE_DEFAULTS,bindings=bindings,text_scale=1.5))
            self.assertEqual(Preferences(prefs.path).values['bindings'],bindings)
            self.assertEqual(Preferences(prefs.path).values['text_scale'],1.5)

    def test_old_preferences_receive_new_defaults_and_are_independent(self):
        old={key:value for key,value in PREFERENCE_DEFAULTS.items() if key not in ('bindings','text_scale')}
        values=validate_preferences(old)
        self.assertEqual(values['bindings'],BINDING_DEFAULTS)
        values['bindings']['forward']='i'
        self.assertEqual(BINDING_DEFAULTS['forward'],'w')

    def test_ui_scaling_only_accepts_supported_values(self):
        for value in (True,0,2,1.1,'1.5'):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_preferences({'text_scale':value})

    def test_defaults_preserve_milestone_five_values(self):
        values = validate_preferences({})
        self.assertEqual(values, PREFERENCE_DEFAULTS)
        self.assertEqual((values['brightness'], values['horror_frequency']), (1, 1))
        self.assertEqual((values['shadow_quality'], values['jumpscare_intensity']), ('low', .65))

    def test_validation_rejects_bad_types_nonfinite_bounds_and_unknown_fields(self):
        cases = ({'brightness': True}, {'brightness': float('nan')}, {'brightness': float('inf')},
                 {'brightness': 0}, {'mouse_sensitivity': 4}, {'horror_frequency': -1},
                 {'jumpscare_intensity': 1.1}, {'reduced_shake': 1}, {'fps_cap': 75},
                 {'fps_cap': True}, {'fps_cap': 60.0}, {'shadow_quality': 'ultra'},
                 {'ghost_difficulty': 'impossible'}, {'unexpected': 1}, [], None)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_preferences(case)

    def test_partial_configuration_is_validated_without_mutating_defaults(self):
        values = validate_preferences({'brightness': 1.7, 'reduced_shake': True})
        self.assertEqual(values['brightness'], 1.7)
        self.assertEqual(PREFERENCE_DEFAULTS['brightness'], 1)
        self.assertEqual(values['shadow_quality'], 'low')

    def test_preferences_roundtrip_is_separate_from_game_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'preferences.json'
            prefs = Preferences(path)
            prefs.save(dict(PREFERENCE_DEFAULTS, ghost_difficulty='relaxed', brightness=1.25, fps_cap=60))
            loaded = Preferences(path)
            self.assertEqual(loaded.values, prefs.values)
            self.assertFalse(loaded.error)
            self.assertEqual(set(json.loads(path.read_text())), {'version','values'})
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_corrupt_unsupported_and_invalid_preferences_fall_back_safely(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'preferences.json'
            for contents in ('{', '[]', '{"version":2,"values":{}}',
                             '{"version":1,"values":{"brightness":99}}'):
                path.write_text(contents)
                prefs = Preferences(path)
                self.assertEqual(prefs.values, PREFERENCE_DEFAULTS)
                self.assertTrue(prefs.error)
                self.assertEqual(path.read_text(), contents)

    def test_failed_atomic_save_preserves_disk_and_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'preferences.json'
            prefs = Preferences(path)
            prefs.save(PREFERENCE_DEFAULTS)
            before = path.read_text()
            with patch('game.settings.os.replace', side_effect=PermissionError()), self.assertRaises(PermissionError):
                prefs.save(dict(PREFERENCE_DEFAULTS, brightness=2))
            self.assertEqual(path.read_text(), before)
            self.assertEqual(prefs.values, PREFERENCE_DEFAULTS)
            self.assertFalse(path.with_suffix('.json.tmp').exists())
            with self.assertRaises(ValueError):
                prefs.save({'brightness':99})
            self.assertEqual(path.read_text(), before)
