"""Reviewed meanings never mutate originals or manufacture physical clocks."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app_channel_store import ChannelStore, Dataset
from app_parameter_contracts import metric_record, result_bundle, strict_json
from app_parameter_inventory import inventory_runs
from app_parameter_profiles import profile_v2, validate_profile_v2
from app_parameter_semantics import (ParameterTemplates2, default_mapping,
    project_field, resolve_mapping, template_scope, validate_mapping, validate_transform)
from app_engineering_units import convert, convert_difference


def source(values, *, x=None, unit='count', raw=None, metadata=None, clock=None):
    values = np.asarray(values)
    frame = pd.DataFrame({'value': values, 'clock': np.arange(len(values), dtype=float) if x is None else x})
    frame.attrs['column_units'] = {'value': unit, 'clock': 's'}
    frame.attrs['inventory_fields'] = {
        'value': {'original_name': 'Synthetic value', 'clock': 'clock', 'coordinate_unit': 's',
            'clock_description': clock or {'kind': 'time', 'trust': 'declared', 'domain': 'relative', 'acquisition_policy': 'sampled'},
            'metadata': metadata or {}},
        'clock': {'original_name': 'Clock', 'disposition': 'supporting clock'}}
    if raw is not None:
        frame.attrs['source_raw_arrays'] = {'value': np.asarray(raw)}
    store = ChannelStore()
    dataset = Dataset('Synthetic run', frame, 'synthetic://fixture')
    store.datasets[dataset.id] = dataset
    field = next(f for f in inventory_runs(store)[0]['fields'] if f['source_key'] == 'value')
    return store, field


def reviewed(field, **changes):
    record = default_mapping(field)
    record.update(structure='analog', encoding={'stored_values': 'raw'},
        authority={'kind': 'user_confirmed', 'source': 'Synthetic hand calculation', 'version': '1', 'reviewed': True},
        acquisition_policy={'mode': 'continuous', 'clock_reviewed': True, 'duplicate_clock': 'reject', 'clock_reset': 'reject'})
    record.update(changes)
    return validate_mapping(record, field)


class ProjectionTests(unittest.TestCase):
    def test_raw_and_reader_engineering_equivalence_exactly_once(self):
        store, field = source([1000., 2000., 3000.], unit='RPM', raw=[100., 200., 300.], metadata={'raw_unit': 'count'})
        before = store.datasets[field['run_id']].frame.copy(deep=True)
        transform = {'op': 'scale_offset', 'scale': 10., 'offset': 0., 'output_unit': 'RPM'}
        raw_map = reviewed(field, unit='RPM', transforms=[transform])
        a = project_field(store, field, raw_map)
        b = project_field(store, field, reviewed(field, unit='RPM', encoding={'stored_values': 'engineering'}, transforms=[transform]))
        c = project_field(store, field, raw_map)
        np.testing.assert_equal(a['values'], [1000, 2000, 3000])
        np.testing.assert_equal(a['values'], b['values'])
        np.testing.assert_equal(a['values'], c['values'])
        self.assertEqual(a['status'], 'computed')
        self.assertEqual(len(a['provenance']['applied_transforms']), 1)
        self.assertEqual(b['provenance']['applied_transforms'], [])
        self.assertEqual(len(b['provenance']['skipped_transforms']), 1)
        pd.testing.assert_frame_equal(store.datasets[field['run_id']].frame, before)
        with self.assertRaises(ValueError):
            a['values'][0] = 0

    def test_opaque_functions_do_not_execute_or_establish_encoding(self):
        store, field = source([5., 8.], metadata={'source_function': "__import__('os').system('false')", 'scaling_active': True})
        projected = project_field(store, field, default_mapping(field))
        self.assertEqual(projected['status'], 'needs_scaling')
        np.testing.assert_equal(projected['values'], [5, 8])
        self.assertIs(projected['provenance']['source_functions_executed'], False)
        explicit = reviewed(field, encoding={'stored_values': 'unresolved'})
        self.assertEqual(project_field(store, field, explicit)['status'], 'needs_scaling')

    def test_constant_numeric_is_not_binary_and_text_is_categorical(self):
        store, field = source([42., 42., 42.], unit='°C')
        self.assertEqual(default_mapping(field)['structure'], 'unknown')
        store, text = source(['IDLE', 'RUN', 'RUN'], unit='')
        self.assertEqual(default_mapping(text)['structure'], 'categorical')
        projected = project_field(store, text, default_mapping(text))
        self.assertEqual(projected['role'], '')
        np.testing.assert_equal(projected['values'], ['IDLE', 'RUN', 'RUN'])

    def test_unreviewed_binary_suggestion_is_not_an_actuator_timeline(self):
        store, field = source([0., 1., 0.])
        suggested = default_mapping(field)
        suggested.update(structure='binary', role='valve')
        projection = project_field(store, field, suggested)
        self.assertEqual(projection['structure'], 'unknown')
        self.assertEqual(projection['role'], '')

    def test_reviewed_unknown_units_support_descriptive_analysis(self):
        store, field = source(['alpha', 'beta'], unit='vendor label')
        mapping = reviewed(field, structure='categorical', unit='vendor label', dimension='unknown')
        self.assertEqual(project_field(store, field, mapping)['status'], 'computed')
        mapping['dimension'] = 'temperature'
        with self.assertRaisesRegex(ValueError, 'unregistered unit'):
            validate_mapping(mapping, field)

    def test_absolute_difference_and_rate_temperature_conversions(self):
        np.testing.assert_allclose(convert([32., 212.], '°F', '°C'), [0., 100.], atol=1e-12)
        np.testing.assert_allclose(convert_difference([9., 18.], '°F', '°C'), [5., 10.])
        np.testing.assert_allclose(convert_difference([9.], '°F/min', '°C/min'), [5.])
        for kind, expected in [('absolute', [0., 100.]), ('difference', [160/9, 1060/9])]:
            store, field = source([32., 212.], unit='°F')
            mapping = reviewed(field, unit='°C', dimension='temperature', transforms=[{
                'op': 'unit_conversion', 'source_unit': '°F', 'target_unit': '°C', 'quantity_kind': kind}])
            projection = project_field(store, field, mapping)
            np.testing.assert_allclose(projection['values'], expected, atol=1e-12)
            self.assertEqual(projection['unit'], '°C')

    def test_missing_conversion_cannot_relabel_known_units(self):
        store, field = source([1000., 2000.], unit='Pa')
        projection = project_field(store, field, reviewed(field, unit='kPa', dimension='pressure'))
        self.assertEqual(projection['status'], 'needs_scaling')
        self.assertEqual(projection['unit'], 'Pa')
        np.testing.assert_equal(projection['values'], [1000, 2000])

    def test_failed_transform_discards_partial_pipeline(self):
        store, field = source([0., 1.])
        mapping = reviewed(field, transforms=[{'op': 'dictionary', 'values': {'0': 'OFF', '1': 'ON'}},
            {'op': 'scale_offset', 'scale': 3., 'output_unit': 'count'}])
        projected = project_field(store, field, mapping)
        self.assertEqual(projected['status'], 'needs_scaling')
        self.assertEqual(projected['provenance']['applied_transforms'], [])
        np.testing.assert_equal(projected['values'], [0, 1])

    def test_sentinels_and_bounded_calibration_preserve_invalid_support(self):
        store, field = source([-999., -1., 5., 11.])
        mapping = reviewed(field, unit='°C', dimension='temperature', transforms=[
            {'op': 'sentinels', 'values': [-999.]},
            {'op': 'calibration', 'id': 'synthetic', 'verified': True, 'x': [0., 10.], 'y': [0., 100.], 'input_unit': 'count', 'output_unit': '°C'}])
        projection = project_field(store, field, mapping)
        np.testing.assert_equal(projection['valid'], [False, False, True, False])
        self.assertEqual(projection['values'][2], 50.)

    def test_documented_signed_decode_and_uint64_mask_have_no_float_rounding(self):
        store, field = source(np.array([65535, 0, 32768], dtype=np.uint16))
        mapping = reviewed(field, transforms=[{'op': 'integer_decode', 'bits': 16, 'signed': True, 'documented': True, 'source': 'Synthetic two-complement schema'}])
        np.testing.assert_equal(project_field(store, field, mapping)['values'], [-1, 0, -32768])
        value = (1 << 63) + 1
        store, field = source(np.array([value], dtype=np.uint64))
        mapping = reviewed(field, transforms=[{'op': 'bit_mask', 'mask': value, 'documented': True, 'source': 'Synthetic packed schema'}])
        self.assertEqual(int(project_field(store, field, mapping)['values'][0]), value)

    def test_missing_clock_stays_in_sample_domain(self):
        store, field = source([2., 3., 4.], clock={'kind': 'sample', 'trust': 'unavailable'})
        projected = project_field(store, field, reviewed(field))
        self.assertIsNone(projected['x_s'])
        self.assertTrue(projected['quality']['timing_reasons'])
        np.testing.assert_equal(projected['source_indices'], [0, 1, 2])

    def test_duplicate_policy_resolves_projection_only(self):
        store, field = source([10., 20., 30.], x=[0., 0., 1.])
        record = reviewed(field)
        self.assertIsNone(project_field(store, field, record)['x_s'])
        for policy, values, indices in [('first', [10, 30], [0, 2]), ('last', [20, 30], [1, 2])]:
            mapping = copy.deepcopy(record)
            mapping['acquisition_policy']['duplicate_clock'] = policy
            projected = project_field(store, field, mapping)
            np.testing.assert_equal(projected['x_s'], [0, 1])
            np.testing.assert_equal(projected['values'], values)
            np.testing.assert_equal(projected['source_indices'], indices)
            self.assertEqual(projected['provenance']['original_sample_count'], 3)
        np.testing.assert_equal(store.datasets[field['run_id']].frame['value'].to_numpy(), [10, 20, 30])

    def test_backward_clock_never_sorts_into_physical_time(self):
        store, field = source([5., 8., 3.], x=[0., 2., 1.])
        projected = project_field(store, field, reviewed(field))
        self.assertIsNone(projected['x_s'])
        self.assertIn('Backward/reset', projected['quality']['timing_reasons'][0])
        np.testing.assert_equal(projected['values'], [5, 8, 3])

    def test_numeric_string_projection_keeps_original_cells(self):
        store, field = source(['10', '20', '30'])
        field['metadata']['numeric_scalar'] = True
        projection = project_field(store, field, default_mapping(field))
        np.testing.assert_equal(projection['values'], [10., 20., 30.])
        self.assertEqual(projection['values'].dtype.kind, 'f')
        np.testing.assert_equal(store.datasets[field['run_id']].frame['value'].to_numpy(), ['10', '20', '30'])


class MappingTemplateTests(unittest.TestCase):
    def test_validation_rejects_unreviewed_transform_and_fake_authority(self):
        store, field = source([1, 2])
        mapping = default_mapping(field)
        mapping['transforms'] = [{'op': 'scale_offset', 'scale': 10}]
        with self.assertRaisesRegex(ValueError, 'reviewed authority'):
            validate_mapping(mapping, field)
        mapping['authority'] = {'kind': 'heuristic', 'reviewed': True}
        with self.assertRaisesRegex(ValueError, 'confirmed or documented'):
            validate_mapping(mapping, field)
        with self.assertRaisesRegex(ValueError, 'Unsupported transform'):
            validate_transform({'op': 'eval', 'expression': '1+1'})

    def test_repeat_or_out_of_order_transform_is_rejected(self):
        store, field = source([1, 2])
        mapping = reviewed(field)
        mapping['transforms'] = [{'op': 'scale_offset', 'scale': 1}, {'op': 'scale_offset', 'scale': 1}]
        with self.assertRaisesRegex(ValueError, 'only once'):
            validate_mapping(mapping, field)
        mapping['transforms'] = [{'op': 'scale_offset', 'scale': 1}, {'op': 'sentinels', 'values': [0]}]
        with self.assertRaisesRegex(ValueError, 'decode before'):
            validate_mapping(mapping, field)

    def test_scoped_templates_reuse_only_compatible_source(self):
        metadata = {'source_schema': 'synthetic-v1', 'device_family': 'fixture', 'firmware_family': 'v1', 'encoding_signature': 'signed16-raw'}
        store, field = source([1, 2], metadata=metadata)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'mappings.json'
            templates = ParameterTemplates2(path)
            templates.save(templates.review(field, reviewed(field, role='custom_force')))
            restored = ParameterTemplates2(path)
            renamed = copy.deepcopy(field)
            renamed['original_name'] = 'A display alias'
            renamed['id'] = 'a-new-import-id'
            match = restored.resolve(renamed)
            self.assertEqual(match['status'], 'matched')
            self.assertEqual(match['mapping']['field_id'], 'a-new-import-id')
            self.assertEqual(match['mapping']['authority']['kind'], 'confirmed_template')
            for key in ('source_schema', 'device_family', 'firmware_family', 'encoding_signature'):
                changed = copy.deepcopy(field)
                changed['metadata'][key] += '-different'
                self.assertEqual(restored.resolve(changed)['status'], 'needs_review')

    def test_incomplete_source_scope_never_silently_reuses(self):
        store, field = source([1, 2])
        with tempfile.TemporaryDirectory() as root:
            templates = ParameterTemplates2(Path(root) / 'mappings.json')
            templates.save(templates.review(field, reviewed(field)))
            self.assertEqual(templates.resolve(field)['status'], 'needs_review')
            self.assertFalse(template_scope(field)['reusable'])

    def test_old_or_corrupt_template_is_preserved_for_review(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'legacy.json'
            original = '{"version":1,"custom":{"name":"Keep me"}}'
            path.write_text(original)
            templates = ParameterTemplates2(path)
            self.assertIn('original file is preserved', templates.warning)
            self.assertEqual(path.read_text(), original)

    def test_profile_alias_is_suggestion_and_identity_is_bound_to_source(self):
        profile = json.loads((Path(__file__).resolve().parents[1] / 'examples/parameter_profiles/force_fixture.json').read_text())
        store, field = source([1, 2], unit='N')
        field['original_name'] = 'Synthetic force'
        mapping = resolve_mapping(field, profile=profile)
        self.assertEqual(mapping['status'], 'needs_mapping')
        self.assertEqual(mapping['authority']['kind'], 'heuristic')
        self.assertEqual(mapping['field_id'], field['id'])
        self.assertEqual(mapping['role'], 'clamping_force')
        self.assertFalse(mapping['authority']['reviewed'])


class ProfileAndEvidenceTests(unittest.TestCase):
    def test_all_bundled_legacy_profiles_adapt_without_changing_source(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root / 'profiles').glob('*.json'):
            if path.name.endswith('schema.json'):
                continue
            before = path.read_bytes()
            original = json.loads(before)
            if original.get('schema_version') != 1:
                continue
            adapted = profile_v2(original)
            self.assertEqual(adapted['schema_version'], 2)
            self.assertEqual(len(adapted['channels']), len(original['channels']))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(original, json.loads(before))
            self.assertEqual(adapted, validate_profile_v2(adapted))
            self.assertTrue(all(not c['mapping']['authority']['reviewed'] for c in adapted['channels']))

    def test_new_domain_role_uses_existing_ops_without_ui_changes(self):
        root = Path(__file__).resolve().parents[1]
        profile = json.loads((root / 'examples/parameter_profiles/force_fixture.json').read_text())
        validated = validate_profile_v2(profile)
        self.assertEqual(validated['channels'][0]['unit'], 'N')
        self.assertEqual(validated['channels'][0]['domain'], 'mechanical_fixture')
        self.assertEqual(validated['roles'][0]['id'], 'clamping_force')
        invalid = copy.deepcopy(profile)
        invalid['kpis'][0]['unit'] = '°C'
        with self.assertRaisesRegex(ValueError, 'output dimension'):
            validate_profile_v2(invalid)

    def test_result_availability_and_acceptance_are_independent(self):
        metric = metric_record('maximum', 10., 'N', role='clamping_force')
        self.assertEqual(metric['status'], 'computed')
        self.assertEqual(metric['acceptance']['status'], 'not_evaluated')
        unavailable = metric_record('settling_time', None, 's', status='missing_input', reasons=['Reference not mapped'])
        bundle = result_bundle('analysis', [], [], [metric, unavailable], provenance={'source': 'synthetic'})
        self.assertEqual(bundle['schema_version'], 2)
        self.assertEqual(json.loads(json.dumps(bundle, allow_nan=False)), bundle)
        self.assertEqual(unavailable['reasons'], ['Reference not mapped'])

    def test_nonfinite_or_malformed_evidence_is_rejected(self):
        for value in (float('nan'), float('inf'), np.float64('nan')):
            with self.assertRaisesRegex(ValueError, 'NaN or infinity'):
                strict_json({'value': value})
        with self.assertRaises(ValueError):
            metric_record('duration', 2., supported_duration_s=-1)
        with self.assertRaises(ValueError):
            metric_record('duration', 2., status='green')
        with self.assertRaises(ValueError):
            result_bundle('analysis', [], [], ['not a record'])


if __name__ == '__main__':
    unittest.main()
