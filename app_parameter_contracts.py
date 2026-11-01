"""Versioned, JSON-only evidence shared by analysis, review and delivery.

Unknown support and uncertainty are represented by None. Result availability,
evidence basis and engineering acceptance are deliberately separate fields.
"""
import math
from collections.abc import Mapping

STRUCTURES = frozenset({'analog', 'quantized_analog', 'binary', 'enum', 'bitfield',
                        'pulse', 'counter', 'countdown', 'setpoint', 'categorical',
                        'metadata', 'unknown'})
RESULT_STATUSES = frozenset({'computed', 'partial', 'not_observed', 'missing_input',
    'needs_mapping', 'needs_scaling', 'needs_review', 'invalid', 'unsupported',
    'not_comparable', 'insufficient_data', 'unavailable', 'cancelled', 'error'})
ACCEPTANCE_STATUSES = frozenset({'pass', 'fail', 'indeterminate', 'not_evaluated'})


def strict_json(value):
    """Copy JSON-compatible evidence, accepting numpy scalars but rejecting NaN.

    Non-finite measurements must be recorded as value=None with an availability
    reason by the caller. Silently serialising NaN loses that distinction.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Evidence must not contain NaN or infinity')
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ValueError('Evidence object keys must be strings')
        return {k: strict_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [strict_json(v) for v in value]
    # Avoid depending on numpy in consumers that only read evidence files.
    if type(value).__module__.split('.')[0] == 'numpy':
        return strict_json(value.tolist())
    raise ValueError('Evidence contains unsupported value type: ' + type(value).__name__)


def metric_record(metric_id, value=None, unit='', *, status='computed', run_id='',
                  field_id='', role='', instance='', scope=None,
                  definition_version='1', evidence_basis='raw observation', **details):
    if not isinstance(metric_id, str) or not metric_id.strip():
        raise ValueError('A metric identifier is required')
    if status not in RESULT_STATUSES:
        raise ValueError('Unknown metric result status: ' + str(status))
    if any(not isinstance(v, str) for v in (unit, run_id, field_id, role, instance,
                                            definition_version, evidence_basis)):
        raise ValueError('Metric identifiers, unit and evidence basis must be strings')
    if not definition_version or not evidence_basis:
        raise ValueError('Metric definition version and evidence basis are required')
    if scope is not None and not isinstance(scope, dict):
        raise ValueError('Metric scope must be an object')
    record = {'metric_id': metric_id, 'definition_version': definition_version,
        'value': value, 'unit': unit, 'status': status, 'run_id': run_id,
        'field_id': field_id, 'role': role, 'instance': instance,
        'scope': scope if scope is not None else {'kind': 'run'},
        'evidence_basis': evidence_basis, 'reasons': [], 'warnings': [],
        'supported_duration_s': None, 'coverage_denominator_s': None,
        'sample_count': None, 'event_count': None, 'boundary_uncertainty_s': None,
        'acceptance': {'status': 'not_evaluated', 'reasons': ['No acceptance rule supplied']},
        'provenance': {}, **details}
    # Fixed identity/status fields cannot be overridden through extra details.
    for key in ('reasons', 'warnings'):
        if not isinstance(record[key], list) or any(not isinstance(v, str) for v in record[key]):
            raise ValueError(key + ' must be a list of explanations')
    acceptance = record['acceptance']
    if not isinstance(acceptance, dict) or acceptance.get('status') not in ACCEPTANCE_STATUSES:
        raise ValueError('Invalid engineering acceptance status')
    if not isinstance(acceptance.get('reasons', []), list) or any(not isinstance(v, str) for v in acceptance.get('reasons', [])):
        raise ValueError('Acceptance reasons must be a list')
    if not isinstance(record['provenance'], dict):
        raise ValueError('Metric provenance must be an object')
    for key in ('supported_duration_s', 'coverage_denominator_s', 'boundary_uncertainty_s'):
        number = record[key]
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)) or number < 0):
            raise ValueError(key + ' must be nonnegative or unknown')
    for key in ('sample_count', 'event_count'):
        count = record[key]
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
            raise ValueError(key + ' must be a nonnegative integer or unknown')
    if status not in ('computed', 'partial') and not record['reasons']:
        record['reasons'] = [status.replace('_', ' ')]
    return strict_json(record)


def result_bundle(kind, runs, inventory, metrics, comparisons=None, events=None,
                  stages=None, pairings=None, readiness=None, quality=None,
                  provenance=None, plot_series=None, **details):
    if kind not in ('analysis', 'comparison'):
        raise ValueError('A result bundle is analysis or comparison')
    lists = {'runs': runs, 'inventory': inventory, 'metrics': metrics,
        'comparisons': comparisons, 'events': events, 'stages': stages,
        'pairings': pairings, 'readiness': readiness, 'quality': quality,
        'plot_series': plot_series}
    for key, value in lists.items():
        if value is not None and not isinstance(value, (list, tuple)):
            raise ValueError(key + ' must be an array')
        if value is not None and any(not isinstance(v, dict) for v in value):
            raise ValueError(key + ' records must be objects')
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError('Result provenance must be an object')
    if set(details) & {'schema_version', 'kind'}:
        raise ValueError('Result bundle identity cannot be overridden')
    return strict_json({'schema_version': 2, 'kind': kind,
        **{key: list(value) if value is not None else [] for key, value in lists.items()},
        'provenance': provenance if provenance is not None else {}, **details})
