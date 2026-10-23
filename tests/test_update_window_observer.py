"""Guard quiet-update acceptance against missing ancestry and title-only checks."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from scripts import check_application_updates as gate


class UpdateWindowObserverTests(unittest.TestCase):
    def test_previous_pins_match_permanent_verified_release_evidence(self):
        evidence=json.loads((gate.ROOT/'docs/validation/release-v2.4.1.json').read_text())
        self.assertEqual(gate.PRIOR_VERSION,evidence['version'])
        for kind,artifact in [('portable','standalone-onefile'),('portable-zip','standalone-folder'),('installer','installed-setup')]:
            pin=gate.PRIOR_ARTIFACTS[kind];actual=evidence['artifacts'][artifact]
            self.assertEqual((pin['name'],pin['size'],pin['sha256']),(actual['filename'],actual['bytes'],actual['sha256']))

    def test_descendants_follow_short_lived_loader_and_exclude_unrelated_windows(self):
        snapshot={10:{'parent':1},11:{'parent':10},12:{'parent':11},13:{'parent':12},99:{'parent':1}}
        self.assertEqual(gate.descendant_pids(snapshot,{10}),{10,11,12,13})
        # A bootstrap parent exited between samples, but its recorded PID still
        # identifies the child engine and that engine's own health-check child.
        after={12:{'parent':11},13:{'parent':12},99:{'parent':1}}
        self.assertEqual(gate.descendant_pids(after,{10,11}),{10,11,12,13})

    def test_image_identity_is_required_and_only_workbench_windows_are_allowed(self):
        allowed=Path('/native-test/new/ApplianceSignalStudio.exe')
        records=[
            {'hwnd':1,'pid':12,'image':str(allowed),'title':'Appliance Signal Studio · 2.4.2','class':'Qt6QWindowIcon'},
            {'hwnd':2,'pid':11,'image':'/native-test/is-temp/setup.tmp','title':'Appliance Signal Studio · 2.4.2','class':'TWizardForm'},
            {'hwnd':3,'pid':12,'image':str(allowed),'title':'Error','class':'#32770'},
            {'hwnd':4,'pid':11,'image':None,'title':'Setup','class':'TWizardForm'},
        ]
        observer=gate.UpdateWindowObserver(10,[allowed])
        with patch.object(gate,'process_snapshot',return_value={10:{'parent':1},11:{'parent':10},12:{'parent':11}}),\
             patch.object(gate,'process_image',side_effect=lambda pid:{10:'/native-test/powershell.exe',11:'/native-test/is-temp/setup.tmp',12:str(allowed)}[pid]),\
             patch.object(gate,'visible_process_windows',return_value=records) as enumerate_windows:
            observer.sample()
        enumerate_windows.assert_called_once_with({10,11,12})
        self.assertEqual({window['hwnd'] for window in observer.report()['unexpected_visible_windows']},{2,3,4})
        with self.assertRaises(AssertionError):observer.assert_hidden()

    def test_hidden_acceptance_requires_observing_the_actual_setup_process(self):
        setup=Path('/native-test/verified-Setup.exe')
        observer=gate.UpdateWindowObserver(10)
        with patch.object(gate,'process_snapshot',return_value={10:{'parent':1},11:{'parent':10}}),\
             patch.object(gate,'process_image',side_effect=lambda pid:str(setup) if pid==11 else '/native-test/powershell.exe'),\
             patch.object(gate,'visible_process_windows',return_value=[]):
            observer.sample()
        observer.assert_hidden(setup)
        with self.assertRaises(AssertionError):observer.assert_hidden('/native-test/unobserved-Setup.exe')
        with self.assertRaises(AssertionError):gate.UpdateWindowObserver(10).assert_hidden()

    def test_native_observation_errors_cannot_be_reported_as_hidden_success(self):
        observer=gate.UpdateWindowObserver(10)
        with patch.object(gate,'process_snapshot',side_effect=OSError('native process enumeration failed')):
            observer.start();observer.thread.join(timeout=2);observer.stop()
        self.assertIn('native process enumeration failed',observer.report()['errors'])
        with self.assertRaises(AssertionError):observer.assert_hidden()

    def test_public_summary_retains_checked_identity_and_drops_machine_paths(self):
        setup=Path('/private-machine/users/test/Setup-2.4.2.exe')
        report={'case':'health-failure','poll_ms':25,'samples':40,
                'family_images':[str(setup),'/private-machine/Temp/is-abc/setup.tmp'],
                'unexpected_visible_windows':[{'hwnd':123,'pid':456,'image':'/private-machine/Temp/is-abc/setup.tmp',
                                               'title':'Machine path /private-machine/Temp','class':'TWizardForm'}],
                'errors':['API failed in /private-machine/Temp']}
        public=gate.public_visibility_summary(report,setup=setup,manual_positive_control=True)
        self.assertTrue(public['setup_process_observed'])
        self.assertTrue(public['exact_image_identity_checked'])
        self.assertTrue(public['manual_first_install_wizard_visible'])
        self.assertTrue(public['hidden_policy_rejected_positive_control'])
        self.assertEqual(public['case'],'health-failure')
        self.assertEqual(public['samples'],40)
        self.assertEqual(public['family_image_names'],['Setup-2.4.2.exe','setup.tmp'])
        self.assertEqual(len(public['errors']),1)
        self.assertNotIn('/private-machine',json.dumps(public))
        # Internal evidence remains exact for observer validation/diagnosis.
        self.assertIn('/private-machine',json.dumps(report))

    @unittest.skipUnless(sys.platform=='win32','Actual Win32 positive control runs on the native Windows gate')
    def test_actual_visible_native_probe_fails_the_hidden_window_policy(self):
        result=gate.check_window_observer_positive_control()
        self.assertGreater(result['samples'],0)
        self.assertFalse(result['errors'])
        self.assertTrue(any(window['title']=='Signal Studio visibility positive control' and window['image']
                            for window in result['unexpected_visible_windows']))


if __name__=='__main__':unittest.main()
