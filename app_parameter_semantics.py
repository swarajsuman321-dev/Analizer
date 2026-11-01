"""Reviewed semantic mappings and immutable projections of original observations.

Source function names are evidence only. This module executes a small validated
registry of transforms; it never evaluates file-provided expressions or code.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from app_parameter_contracts import STRUCTURES, RESULT_STATUSES, strict_json
from app_engineering_units import UNITS, unit, convert, convert_difference, calibrated

AUTHORITY_KINDS = {'unresolved', 'user_confirmed', 'confirmed_template',
                   'documented_schema', 'compatible_metadata', 'heuristic'}
SIGNAL_KINDS = {'unknown', 'measurement', 'command', 'feedback', 'reference', 'context', 'status'}
TRANSFORM_REGISTRY = {
    'sentinels': {'version': '1', 'parameters': {'values'}},
    'integer_decode': {'version': '1', 'parameters': {'bits', 'signed', 'documented', 'source'}},
    'scale_offset': {'version': '1', 'parameters': {'scale', 'offset', 'output_unit'}},
    'dictionary': {'version': '1', 'parameters': {'values', 'unknown'}},
    'bit_mask': {'version': '1', 'parameters': {'mask', 'shift', 'documented', 'source'}},
    'calibration': {'version': '1', 'parameters': {'id', 'verified', 'x', 'y', 'input_unit', 'output_unit'}},
    'unit_conversion': {'version': '1', 'parameters': {'source_unit', 'target_unit', 'quantity_kind'}},
}
MAPPING_KEYS = {'schema_version', 'field_id', 'source_identity', 'display_name',
    'structure', 'role', 'instance', 'location', 'function', 'signal_kind', 'domain',
    'unit', 'dimension', 'encoding', 'transforms', 'authority', 'state_dictionary',
    'decoder', 'acquisition_policy', 'status', 'reasons', 'candidates', 'provenance',
    'counter_policy', 'direction', 'parameters', 'canonical_id'}
ACQUISITION_KEYS = {'mode', 'max_gap_seconds', 'clock_reviewed', 'clock_reset',
    'duplicate_clock', 'clock_domain', 'timing_uncertainty_s', 'reviewed',
    'clock_origin', 'sample_interval_s'}


def _number(value, label, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + ' must be finite')
    if minimum is not None and value < minimum:
        raise ValueError(label + ' is below its permitted range')


def _keys(record, allowed, label):
    if not isinstance(record, dict):
        raise ValueError(label + ' must be an object')
    extra = set(record) - set(allowed)
    if extra:
        raise ValueError('Unknown ' + label + ' keys: ' + ', '.join(sorted(extra)))


def validate_transform(record):
    if not isinstance(record, dict) or record.get('op') not in TRANSFORM_REGISTRY:
        raise ValueError('Unsupported transform operation')
    definition = TRANSFORM_REGISTRY[record['op']]
    _keys(record, {'op', 'version', *definition['parameters']}, 'transform')
    if str(record.get('version', '1')) != definition['version']:
        raise ValueError('Unsupported transform version')
    op = record['op']
    if op == 'sentinels':
        if not isinstance(record.get('values'), list):
            raise ValueError('Sentinels require an explicit value list')
    elif op == 'integer_decode':
        bits = record.get('bits')
        if isinstance(bits, bool) or not isinstance(bits, int) or not 1 <= bits <= 64:
            raise ValueError('Integer decoding requires a bit width between 1 and 64')
        if not isinstance(record.get('signed'), bool):
            raise ValueError('Integer decoding requires explicit signedness')
        if record.get('documented') is not True or not record.get('source'):
            raise ValueError('Integer decoding requires documented authority')
    elif op == 'scale_offset':
        _number(record.get('scale', 1), 'Scale')
        _number(record.get('offset', 0), 'Offset')
        if 'output_unit' in record and unit(record['output_unit']) not in UNITS:
            raise ValueError('Unknown scale output unit')
    elif op == 'dictionary':
        if not isinstance(record.get('values'), dict) or not record['values']:
            raise ValueError('Dictionary transform requires an explicit dictionary')
        if record.get('unknown', 'preserve') not in ('preserve', 'invalid'):
            raise ValueError('Dictionary unknown policy must preserve or invalidate')
        if any(not isinstance(v, (str, int, float, bool)) for v in record['values'].values()):
            raise ValueError('Dictionary results must be scalar values')
    elif op == 'bit_mask':
        mask, shift = record.get('mask'), record.get('shift', 0)
        if isinstance(mask, bool) or not isinstance(mask, int) or mask <= 0 or mask >= 2**64:
            raise ValueError('Documented bit mask must be a positive 64-bit integer')
        if isinstance(shift, bool) or not isinstance(shift, int) or not 0 <= shift < 64:
            raise ValueError('Bit shift must be between 0 and 63')
        if record.get('documented') is not True or not record.get('source'):
            raise ValueError('Bit masks require documented authority')
    elif op == 'calibration':
        if record.get('verified') is not True or not record.get('id'):
            raise ValueError('Calibration must be verified and identified')
        x, y = record.get('x'), record.get('y')
        if not isinstance(x, list) or not isinstance(y, list) or len(x) < 2 or len(x) != len(y):
            raise ValueError('Calibration requires paired points')
        for v in x + y:
            _number(v, 'Calibration point')
        if any(a >= b for a, b in zip(x, x[1:])):
            raise ValueError('Calibration X must increase')
        if any(unit(record.get(k, '')) not in UNITS for k in ('input_unit', 'output_unit')):
            raise ValueError('Unknown calibration units')
    elif op == 'unit_conversion':
        kind = record.get('quantity_kind', 'absolute')
        if kind not in ('absolute', 'difference', 'rate'):
            raise ValueError('Declare absolute, difference or rate conversion')
        source, target = (unit(record.get(k, '')) for k in ('source_unit', 'target_unit'))
        convert_difference([0.], source, target)
    return strict_json({**record, 'version': '1'})


def default_mapping(field):
    source_unit = str(field.get('unit') or '')
    # Dtype is structural evidence. Magnitude, number of levels and names are
    # deliberately not used to infer appliance meaning or ON/OFF semantics.
    dtype = str(field.get('dtype', ''))
    disposition = field.get('disposition')
    numeric_projection = bool(field.get('channel_id') or (field.get('metadata') or {}).get('numeric_scalar'))
    structural_default = ('metadata' if disposition in ('supporting clock', 'quality/status source', 'metadata')
                          else 'categorical' if not numeric_projection and dtype.startswith(('object', 'string', 'str', '<U', '|S')) else 'unknown')
    structure = field.get('structure', structural_default)
    if structure not in STRUCTURES:
        structure = 'unknown'
    return {'schema_version': 2, 'field_id': str(field.get('field_id', field.get('id', ''))),
        'source_identity': str(field.get('source_identity', field.get('source_key', field.get('source_path', '')))),
        'display_name': str(field.get('name', field.get('original_name', ''))),
        'structure': structure, 'role': '', 'instance': '', 'location': '', 'function': '',
        'signal_kind': 'unknown', 'domain': '', 'unit': source_unit,
        'dimension': UNITS.get(unit(source_unit), ('unknown',))[0] if source_unit else '',
        'encoding': {'stored_values': 'unresolved'}, 'transforms': [],
        'authority': {'kind': 'unresolved', 'source': '', 'version': '1', 'reviewed': False},
        'state_dictionary': {}, 'decoder': {},
        'acquisition_policy': {'mode': 'sample_only', 'max_gap_seconds': None,
            'clock_reviewed': False, 'clock_reset': 'reject', 'duplicate_clock': 'reject',
            'clock_domain': '', 'timing_uncertainty_s': None},
        'status': 'needs_mapping', 'reasons': ['Semantic meaning has not been reviewed']}


def validate_mapping(mapping, field=None):
    _keys(mapping, MAPPING_KEYS, 'mapping')
    result = default_mapping(field or {})
    result.update(copy.deepcopy(mapping))
    if field:
        identity = default_mapping(field)
        result['field_id'], result['source_identity'] = identity['field_id'], identity['source_identity']
        if not result.get('display_name'):
            result['display_name'] = identity['display_name']
    if result['schema_version'] != 2 or result['structure'] not in STRUCTURES:
        raise ValueError('Unsupported parameter mapping schema or structure')
    for key in ('field_id', 'source_identity', 'display_name', 'role', 'instance', 'location',
                'function', 'signal_kind', 'domain', 'unit', 'dimension'):
        if not isinstance(result[key], str):
            raise ValueError(key + ' must be a string')
    if result['signal_kind'] not in SIGNAL_KINDS:
        raise ValueError('Unknown command/feedback kind')
    if result.get('status') not in RESULT_STATUSES:
        raise ValueError('Unknown mapping status')
    if not isinstance(result.get('reasons'), list) or any(not isinstance(v, str) for v in result['reasons']):
        raise ValueError('Mapping reasons must be a list of explanations')
    encoding = result['encoding']
    _keys(encoding, {'stored_values', 'signature', 'dtype', 'signed', 'bits', 'source_function',
                     'version', 'direction_encoding', 'raw_unit', 'engineering_unit'}, 'encoding')
    if encoding.get('stored_values', 'unresolved') not in ('unresolved', 'raw', 'engineering'):
        raise ValueError('Stored values must explicitly declare raw or engineering encoding')
    if 'signed' in encoding and not isinstance(encoding['signed'], bool):
        raise ValueError('Signedness must be a boolean')
    for key in ('raw_unit', 'engineering_unit'):
        if key in encoding and not isinstance(encoding[key], str):
            raise ValueError(key + ' must be a string')
    if 'bits' in encoding and (isinstance(encoding['bits'], bool) or not isinstance(encoding['bits'], int) or not 1 <= encoding['bits'] <= 64):
        raise ValueError('Encoding width must be between 1 and 64 bits')
    authority = result['authority']
    _keys(authority, {'kind', 'source', 'version', 'reviewed'}, 'mapping authority')
    if authority.get('kind', 'unresolved') not in AUTHORITY_KINDS or not isinstance(authority.get('reviewed', False), bool):
        raise ValueError('Invalid mapping authority')
    for key in ('source', 'version'):
        if key in authority and not isinstance(authority[key], str):
            raise ValueError('Authority ' + key + ' must be a string')
    if authority.get('reviewed') and authority.get('kind', 'unresolved') in ('unresolved', 'heuristic'):
        raise ValueError('A reviewed mapping requires confirmed or documented authority')
    if not isinstance(result['transforms'], list):
        raise ValueError('Transforms must be a list')
    result['transforms'] = [validate_transform(t) for t in result['transforms']]
    # A repeated pipeline operation is almost always a restored/double-applied map.
    ops = [t['op'] for t in result['transforms']]
    if len(ops) != len(set(ops)):
        raise ValueError('A transform operation may occur only once in a projection')
    order = {'sentinels': 0, 'integer_decode': 1, 'dictionary': 1, 'bit_mask': 1, 'scale_offset': 2,
             'calibration': 3, 'unit_conversion': 4}
    if [order[o] for o in ops] != sorted(order[o] for o in ops):
        raise ValueError('Transforms must decode before scaling, calibration and unit normalisation')
    if not isinstance(result['state_dictionary'], dict) or any(not isinstance(k, str) or not isinstance(v, (str, int, float, bool)) for k, v in result['state_dictionary'].items()):
        raise ValueError('State dictionary requires string codes and scalar labels')
    _keys(result['decoder'], {'id', 'version', 'documented', 'source'}, 'decoder')
    if result['decoder'] and (not result['decoder'].get('id') or not result['decoder'].get('source') or result['decoder'].get('documented') is not True):
        raise ValueError('A decoder requires an identifier and documented source')
    policy = result['acquisition_policy']
    _keys(policy, ACQUISITION_KEYS, 'acquisition policy')
    if policy.get('mode', 'sample_only') not in ('sample_only', 'continuous', 'held', 'event'):
        raise ValueError('Unsupported acquisition mode')
    if policy.get('clock_reset', 'reject') != 'reject':
        raise ValueError('Reset clocks require a documented reader clock policy')
    if policy.get('duplicate_clock', 'reject') not in ('reject', 'last', 'first'):
        raise ValueError('Unknown duplicate clock policy')
    for key in ('clock_reviewed', 'reviewed'):
        if key in policy and not isinstance(policy[key], bool):
            raise ValueError(key + ' must be a boolean')
    for key in ('max_gap_seconds', 'timing_uncertainty_s', 'sample_interval_s'):
        if policy.get(key) is not None:
            _number(policy[key], key, 0)
    physical_transforms = any(t['op'] in ('scale_offset', 'calibration', 'unit_conversion') for t in result['transforms'])
    if physical_transforms and unit(result['unit']) not in UNITS:
        raise ValueError('Physical transforms require a registered output unit')
    if unit(result['unit']) in UNITS:
        actual_dimension = UNITS[unit(result['unit'])][0]
        if result['dimension'] and result['dimension'] != actual_dimension:
            raise ValueError('Mapping unit and dimension disagree')
        result['dimension'] = actual_dimension
    elif result['dimension'] not in ('', 'unknown'):
        raise ValueError('An unregistered unit cannot assert a physical dimension')
    if result['transforms'] and not authority.get('reviewed'):
        raise ValueError('Transforms require reviewed authority')
    if not isinstance(result.get('parameters', {}), dict):
        raise ValueError('Capability parameters must be an object')
    if not isinstance(result.get('direction', {}), (dict, str)):
        raise ValueError('Direction encoding must be an object or identifier')
    if 'counter_policy' in result:
        _keys(result['counter_policy'], {'reset', 'modulus', 'source', 'maximum_increment'}, 'counter policy')
        if result['counter_policy'].get('reset', 'unresolved') not in ('unresolved', 'split', 'rollover'):
            raise ValueError('Unknown counter reset policy')
        for key in ('modulus', 'maximum_increment'):
            if key in result['counter_policy']:
                _number(result['counter_policy'][key], key, 0)
        if result['counter_policy'].get('reset') == 'rollover' and (not result['counter_policy'].get('modulus') or not result['counter_policy'].get('source')):
            raise ValueError('Counter rollover requires a documented modulus')
    return strict_json(result)


def _explicit_mapping(field, mappings):
    if not mappings:
        return None
    if isinstance(mappings, dict) and 'structure' in mappings:
        return mappings
    keys = [field.get(k) for k in ('field_id', 'id', 'channel_id', 'source_identity', 'source_key', 'source_path')]
    for key in keys:
        if key is not None and key in mappings:
            return mappings[key]
    return None


def resolve_mapping(field, mappings=None, profile=None):
    """Resolve explicit reviews first; profile aliases remain review suggestions."""
    explicit = _explicit_mapping(field, mappings)
    if isinstance(explicit, dict):
        result = validate_mapping(explicit, field)
        reviewed = result['authority'].get('reviewed', False)
        result['status'] = 'computed' if reviewed else 'needs_mapping'
        result['reasons'] = [] if reviewed else ['Mapping authority has not been reviewed']
        return result
    result = default_mapping(field)
    # Source mapping is valid only if the source explicitly documents its schema.
    metadata = field.get('metadata') or {}
    documented = metadata.get('parameter_mapping')
    if isinstance(documented, dict) and documented.get('authority', {}).get('kind') == 'documented_schema':
        return resolve_mapping(field, documented)
    if profile:
        from app_parameter_profiles import profile_v2
        profile = profile_v2(profile)
        candidates = []
        source_names = {str(field.get(k, '')).casefold() for k in ('name', 'original_name', 'source_identity', 'source_key')}
        for definition in profile['channels']:
            aliases = {str(v).casefold() for v in [definition['id'], definition.get('name', ''), *definition.get('aliases', [])]}
            if source_names & (aliases - {''}):
                candidates.append(definition['id'])
        result['candidates'] = candidates
        if len(candidates) == 1:
            definition = next(c for c in profile['channels'] if c['id'] == candidates[0])
            proposed = definition.get('mapping', {})
            result.update({k: copy.deepcopy(v) for k, v in proposed.items() if k not in ('authority', 'transforms', 'field_id', 'source_identity', 'display_name', 'status', 'reasons')})
            result['canonical_id'] = definition['id']
            result['authority'] = {'kind': 'heuristic', 'source': 'profile alias: ' + profile['id'], 'version': '1', 'reviewed': False}
            result['reasons'] = ['Profile alias suggests a mapping; confirm meaning, encoding and acquisition policy']
        elif len(candidates) > 1:
            result['reasons'] = ['Competing profile mappings require review']
    return validate_mapping(result, field)


def _readonly(values, dtype=None):
    result = np.array(values, dtype=dtype, copy=True)
    result.setflags(write=False)
    return result


def _valid(values):
    if values.dtype.kind in 'iufb':
        return np.isfinite(values)
    if values.dtype.kind == 'c' or values.ndim != 1:
        return np.zeros(len(values), dtype=bool)
    return np.array([v is not None and not (isinstance(v, float) and not math.isfinite(v)) for v in values], bool)


def _code(value):
    if isinstance(value, (float, np.floating)) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value)


def project_field(store, field, mapping):
    """Read originals every time: restoring/reusing a mapping cannot scale twice."""
    from app_parameter_inventory import source_field
    source = source_field(store, field)
    mapping = validate_mapping(mapping, field)
    authority = mapping['authority']
    reviewed = authority.get('reviewed', False)
    stored = mapping['encoding'].get('stored_values', 'unresolved')
    raw = source.get('raw_values')
    if raw is None:
        raw = source['values']
    values = _readonly(source['values'] if stored == 'engineering' else raw)
    numeric_structures = {'analog', 'quantized_analog', 'counter', 'countdown', 'setpoint', 'bitfield', 'pulse', 'binary'}
    if values.ndim == 1 and values.dtype.kind in 'OUS' and (
            mapping['structure'] in numeric_structures or mapping['structure'] == 'unknown' and (
                field.get('channel_id') or (field.get('metadata') or {}).get('numeric_scalar'))):
        import pandas as pd
        # Source cells remain unchanged. Failed numeric cells are invalid in
        # this declared scalar projection rather than silently disappearing.
        values = _readonly(pd.to_numeric(pd.Series(values), errors='coerce').to_numpy(dtype=float))
    valid = _valid(values)
    source_valid = np.asarray(source.get('quality_valid', np.ones(len(values), bool)), bool)
    if source_valid.shape != valid.shape:
        raise ValueError('Source quality mask must match the original observations')
    valid &= source_valid
    source_metadata = source.get('metadata') or {}
    if stored == 'engineering':
        source_unit = str(mapping['encoding'].get('engineering_unit', field.get('unit') or ''))
    else:
        source_unit = str(mapping['encoding'].get('raw_unit', source_metadata.get('raw_unit', field.get('unit') or '')))
    current_unit = source_unit
    status = 'computed' if reviewed else 'needs_mapping'
    reasons = [] if reviewed else ['Semantic mapping has not been reviewed; raw observation only']
    applied, skipped = [], []
    transforms = mapping['transforms']
    opaque = any(source_metadata.get(k) for k in ('source_function', 'scaling_function', 'scale_function', 'scaling_active'))
    if stored == 'unresolved' and reviewed:
        status = 'needs_scaling'
        reasons.append('Stored raw versus engineering encoding is unresolved; no physical transform applied')
    elif stored == 'unresolved' and opaque:
        status = 'needs_scaling'
        reasons.append('Source scaling flags/functions do not prove whether stored values are raw or engineering values')
    elif transforms and reviewed and stored != 'unresolved':
        working = np.array(values, copy=True)
        try:
            for operation in transforms:
                op = operation['op']
                # Engineering observations already include their documented
                # raw decoding/scaling. Only a requested unit normalisation or
                # validity mask applies to that representation.
                if stored == 'engineering' and op not in ('sentinels', 'unit_conversion'):
                    skipped.append({**copy.deepcopy(operation), 'reason': 'Stored values reviewed as already in engineering units'})
                    continue
                if op == 'sentinels':
                    for sentinel in operation['values']:
                        valid &= working != sentinel
                elif op == 'integer_decode':
                    bits = operation['bits']
                    modulus = 1 << bits
                    decoded, good = [], []
                    for value in working:
                        # Python integers avoid float rounding at uint64 limits.
                        try:
                            number = int(value)
                            usable = bool(number == value and 0 <= number < modulus)
                        except (ValueError, TypeError, OverflowError):
                            number, usable = 0, False
                        if usable and operation['signed'] and number >= (1 << (bits - 1)):
                            number -= modulus
                        decoded.append(number if usable else 0)
                        good.append(usable)
                    valid &= np.asarray(good, bool)
                    working = np.array(decoded, dtype=np.int64 if operation['signed'] else np.uint64)
                elif op == 'dictionary':
                    dictionary = operation['values']
                    known = np.array([_code(v) in dictionary for v in working])
                    decoded = [dictionary.get(_code(v), v) for v in working]
                    # Object avoids coercing opaque numeric codes into string labels.
                    numeric_results = all(isinstance(v, (int, float, bool, np.integer, np.floating, np.bool_)) for v in decoded)
                    working = np.array(decoded) if numeric_results else np.array(decoded, dtype=object)
                    if operation.get('unknown') == 'invalid':
                        valid &= known
                    if not known.all():
                        reasons.append('Unmapped dictionary codes preserved' if operation.get('unknown', 'preserve') == 'preserve' else 'Unmapped dictionary codes are invalid')
                        status = 'partial'
                elif op == 'bit_mask':
                    converted, integer = [], []
                    for value in working:
                        try:
                            number = int(value)
                            usable = bool(number == value and 0 <= number < 2**64)
                        except (ValueError, TypeError, OverflowError):
                            number, usable = 0, False
                        converted.append(number if usable else 0)
                        integer.append(usable)
                    valid &= np.asarray(integer, bool)
                    safe = np.array(converted, dtype=np.uint64)
                    working = (safe & np.uint64(operation['mask'])) >> np.uint64(operation.get('shift', 0))
                elif op == 'scale_offset':
                    working = np.asarray(working, float) * operation.get('scale', 1) + operation.get('offset', 0)
                    current_unit = operation.get('output_unit', current_unit)
                elif op == 'calibration':
                    working = calibrated(convert(working, current_unit, operation['input_unit']), operation, operation['output_unit'])
                    current_unit = operation['output_unit']
                elif op == 'unit_conversion':
                    if unit(current_unit) != unit(operation['source_unit']):
                        raise ValueError('Unit conversion source disagrees with the preceding transform')
                    conversion = convert if operation.get('quantity_kind', 'absolute') == 'absolute' else convert_difference
                    working = conversion(working, current_unit, operation['target_unit'])
                    current_unit = operation['target_unit']
                applied.append(copy.deepcopy(operation))
            values = _readonly(working)
            valid &= _valid(values)
        except (ValueError, TypeError, OverflowError) as exc:
            # A failed pipeline never exposes half-transformed observations.
            values = _readonly(source['values'] if stored == 'engineering' else raw)
            valid = _valid(values) & source_valid
            current_unit = source_unit
            applied, skipped = [], []
            status = 'needs_scaling'
            reasons.append('Transform rejected: ' + str(exc))
    if reviewed and stored != 'unresolved' and not transforms:
        # A supplied mapping unit can fill missing metadata, but cannot relabel
        # a known unit without actually converting the observations.
        if source_unit and mapping['unit'] and unit(source_unit) != unit(mapping['unit']):
            status = 'needs_scaling'
            reasons.append('Source and reviewed units differ; declare an explicit unit conversion')
        elif not source_unit:
            current_unit = mapping['unit']
    if reviewed and stored != 'unresolved' and transforms and unit(current_unit) != unit(mapping['unit']):
        status = 'needs_scaling'
        reasons.append('Final transform unit differs from reviewed output unit')
    clock = source.get('clock') or {}
    policy = copy.deepcopy(mapping['acquisition_policy'])
    mode_map = {'sampled': 'continuous', 'held_state': 'held', 'event_log': 'event'}
    # A reader-declared acquisition policy is explicit evidence, not a heuristic.
    if policy.get('mode', 'sample_only') == 'sample_only' and clock.get('trust') == 'declared' and not reviewed:
        policy['mode'] = mode_map.get(clock.get('acquisition_policy'), 'sample_only')
    coordinates = source.get('coordinates', source.get('x'))
    t = np.asarray(coordinates, float) if coordinates is not None else np.array([], float)
    timing_reasons = []
    physical_clock = clock.get('kind') == 'time' and (clock.get('trust') == 'declared' or policy.get('clock_reviewed') is True)
    if not physical_clock or policy.get('mode', 'sample_only') == 'sample_only':
        timing_reasons.append('Trustworthy timebase and acquisition policy are not established; sample-domain analysis only')
    elif t.shape != (len(values),) or not np.isfinite(t).all():
        timing_reasons.append('Native clock has missing or mismatched timestamps')
    elif np.any(np.diff(t) < 0) or (clock.get('quality') or {}).get('backwards', 0) or (clock.get('quality') or {}).get('resets', 0):
        timing_reasons.append('Backward/reset clock requires a documented reader policy; original sample order retained')
    elif np.any(np.diff(t) == 0) and policy.get('duplicate_clock', 'reject') == 'reject':
        timing_reasons.append('Duplicate clock requires an explicit first/last observation policy')
    indices = np.asarray(source.get('source_indices', np.arange(len(values))), dtype=np.int64)
    if indices.shape != (len(values),):
        raise ValueError('Source indices must match the original observations')
    original_count = len(values)
    if not timing_reasons and len(t) > 1 and np.any(np.diff(t) == 0):
        # Resolve duplicate observations only in this disposable projection.
        # Native source order/arrays remain in inventory for audit and reuse.
        keep = np.r_[np.diff(t) != 0, True] if policy.get('duplicate_clock') == 'last' else np.r_[True, np.diff(t) != 0]
        t, values, valid, indices = t[keep], _readonly(values[keep]), valid[keep], indices[keep]
    x_s = None if timing_reasons else _readonly(t, float)
    quality = {'valid_samples': int(valid.sum()), 'sample_count': len(values),
        'invalid_samples': int((~valid).sum()), 'timing_available': x_s is not None,
        'timing_reasons': timing_reasons, 'clock': copy.deepcopy(clock),
        'source_quality': copy.deepcopy(field.get('quality', {}))}
    return {'values': values, 'x_s': x_s, 'source_indices': _readonly(indices, np.int64),
        'valid': _readonly(valid, bool), 'unit': str(current_unit),
        'structure': mapping['structure'] if reviewed else default_mapping(field)['structure'],
        'role': mapping['role'] if reviewed else '',
        'instance': mapping['instance'], 'location': mapping['location'],
        'function': mapping['function'], 'signal_kind': mapping['signal_kind'],
        'dimension': UNITS.get(unit(current_unit), ('unknown',))[0],
        'acquisition_policy': policy, 'quality': quality, 'status': status,
        'reasons': reasons, 'state_dictionary': copy.deepcopy(mapping['state_dictionary']),
        'provenance': {'source_field_id': mapping['field_id'], 'source_identity': mapping['source_identity'],
            'source_arrays': 'original observations', 'mapping': mapping,
            'applied_transforms': applied, 'skipped_transforms': skipped,
            'original_sample_count': original_count,
            'duplicate_clock_policy': policy.get('duplicate_clock', 'reject'), 'authority': authority,
            'stored_values': stored, 'source_functions_executed': False}}


def template_scope(field):
    """Scope includes documented schema/device/firmware and encoding, never label."""
    metadata = field.get('metadata') or {}
    explicit = metadata.get('template_scope') or field.get('template_scope') or {}
    identity = field.get('source_identity') or field.get('source_key') or field.get('source_path') or metadata.get('source_column')
    sources = [explicit, metadata, *(metadata.get(k) or {} for k in ('source_properties', 'group_properties', 'file_properties'))]
    def documented(*keys):
        return next((source[key] for source in sources if isinstance(source, dict) for key in keys if source.get(key) not in (None, '')), None)
    schema = documented('source_schema', 'schema_id')
    device = documented('device_family', 'device_model')
    firmware = documented('firmware_family', 'firmware_version')
    signature = documented('encoding_signature')
    if not signature:
        encoding = {k: documented(k) for k in ('dtype', 'signed', 'bits', 'raw_unit', 'source_function', 'scaling_function', 'reader_operations') if documented(k) is not None}
        encoding.update({'datatype': field.get('datatype', field.get('dtype')), 'unit': field.get('unit')})
        signature = hashlib.sha256(json.dumps(strict_json(encoding), sort_keys=True).encode()).hexdigest()
    return {'source_identity': str(identity or ''), 'source_schema': str(schema or ''),
        'device_family': str(device or ''), 'firmware_family': str(firmware or ''),
        'encoding_signature': str(signature),
        'reusable': bool(identity and schema and device and firmware)}


class ParameterTemplates2:
    """Scoped reviewed mappings; legacy v1 labels remain intact and reviewable."""
    def __init__(self, path=None):
        if path is None:
            from app_output import output_path
            path = output_path('parameter-mappings-v2.json', 'templates')
        self.path = Path(path)
        self.entries = {}
        self.warning = ''
        if self.path.exists():
            try:
                record = json.loads(self.path.read_text(encoding='utf-8'))
                if record.get('schema_version') != 2 or not isinstance(record.get('parameters'), dict):
                    raise ValueError('Unsupported reviewed parameter template schema')
                for key, entry in record['parameters'].items():
                    self._validate_entry(entry)
                    self.entries[key] = entry
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                self.entries = {}
                self.warning = 'Saved semantic mappings require review: ' + str(exc) + '. The original file is preserved.'

    @staticmethod
    def _validate_entry(entry):
        _keys(entry, {'scope', 'mapping'}, 'template entry')
        scope = entry.get('scope')
        _keys(scope, {'source_identity', 'source_schema', 'device_family', 'firmware_family', 'encoding_signature', 'reusable'}, 'template scope')
        if any(not isinstance(scope.get(k), str) for k in ('source_identity', 'source_schema', 'device_family', 'firmware_family', 'encoding_signature')):
            raise ValueError('Template scope requires explicit schema/device/firmware/encoding strings')
        if not isinstance(scope.get('reusable'), bool):
            raise ValueError('Template scope requires an explicit reuse flag')
        if scope['reusable'] and not all(scope[k] for k in ('source_identity', 'source_schema', 'device_family', 'firmware_family', 'encoding_signature')):
            raise ValueError('Reusable templates require complete schema/device/firmware/encoding identity')
        mapping = validate_mapping(entry.get('mapping'))
        if not mapping['authority'].get('reviewed'):
            raise ValueError('Only reviewed mappings can be saved')

    def review(self, field, mapping):
        reviewed = validate_mapping(mapping, field)
        if not reviewed['authority'].get('reviewed'):
            raise ValueError('Confirm mapping authority before saving a review')
        scope = template_scope(field)
        key = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        return {key: {'scope': scope, 'mapping': reviewed}}

    def save(self, entries):
        if not isinstance(entries, dict):
            raise ValueError('Template entries must be an object returned by review')
        for entry in entries.values():
            self._validate_entry(entry)
        updated = {**self.entries, **copy.deepcopy(entries)}
        from app_support import atomic_output
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with atomic_output(self.path) as temporary:
            Path(temporary).write_text(json.dumps(strict_json({'schema_version': 2, 'parameters': updated}), ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        self.entries = updated

    def resolve(self, field):
        scope = template_scope(field)
        candidates = [e for e in self.entries.values() if e['scope']['source_identity'] == scope['source_identity']]
        matches = [e for e in candidates if scope['reusable'] and e['scope'].get('reusable') and e['scope'] == scope]
        if len(matches) == 1:
            mapping = copy.deepcopy(matches[0]['mapping'])
            mapping.update(field_id=str(field.get('field_id', field.get('id', ''))), status='computed', reasons=[])
            mapping['authority'] = {**mapping['authority'], 'kind': 'confirmed_template'}
            return {'status': 'matched', 'mapping': mapping, 'reasons': []}
        reasons = ['Saved mapping schema, device/firmware or encoding differs; review required'] if candidates else ['No compatible reviewed mapping']
        if not scope['reusable']:
            reasons = ['Source schema/device/firmware scope is incomplete; review required before template reuse']
        return {'status': 'needs_review', 'mapping': None, 'reasons': reasons}

    def unknown(self, fields):
        return [field for field in fields if self.resolve(field)['status'] != 'matched']
