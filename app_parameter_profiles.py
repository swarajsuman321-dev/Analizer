"""Schema-2 declarative roles validated against bounded operation capabilities.

Custom roles/domains are data. A new algorithm still requires a trusted Python
registration; a profile cannot provide executable source or arbitrary operators.
"""
import copy
import re
from app_engineering_units import UNITS, unit
from app_parameter_contracts import STRUCTURES, strict_json
from app_parameter_semantics import validate_mapping

NUMERIC = {'analog', 'quantized_analog', 'setpoint', 'unknown'}
OPERATION_CAPABILITIES = {
    op: {'version': '1', 'structures': sorted(NUMERIC), 'timing': op in {'integral', 'mean', 'std', 'rms', 'slope'}}
    for op in ('integral', 'mean', 'max', 'min', 'std', 'rms', 'first', 'last', 'slope', 'absmax', 'difference', 'ratio')}
OPERATION_CAPABILITIES.update({
    'duration': {'version': '1', 'structures': sorted(STRUCTURES - {'metadata', 'unknown'}), 'timing': True},
    'counter': {'version': '1', 'structures': ['counter'], 'timing': False},
    'on_duration': {'version': '1', 'structures': ['binary'], 'timing': True},
    'pulse_volume': {'version': '1', 'structures': ['pulse', 'counter', 'binary'], 'timing': False},
})
PROFILE_KEYS = {'schema_version', 'id', 'category', 'metadata', 'domains', 'roles',
    'channels', 'operations', 'phases', 'kpis', 'tolerances', 'acceptance', 'anomalies',
    'calibrations', 'extensions', 'migration'}


def _object(record, keys, label):
    if not isinstance(record, dict) or set(record) - set(keys):
        raise ValueError('Invalid or unknown ' + label + ' keys')


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_]*', value)


def validate_profile_v2(record):
    _object(record, PROFILE_KEYS, 'schema-2 profile')
    if record.get('schema_version') != 2:
        raise ValueError('Expected profile schema 2')
    if not _identifier(record.get('id')) or not isinstance(record.get('category'), str) or not record['category'].strip():
        raise ValueError('Profile requires an identifier and category')
    for key in ('domains', 'roles', 'channels', 'operations', 'phases', 'kpis', 'anomalies'):
        if not isinstance(record.get(key, []), list):
            raise ValueError(key + ' must be an array')
    for key in ('metadata', 'tolerances', 'acceptance', 'calibrations', 'extensions', 'migration'):
        if not isinstance(record.get(key, {}), dict):
            raise ValueError(key + ' must be an object')
    dimensions = {definition[0] for definition in UNITS.values()} | {'unknown'}
    domains = {}
    for domain in record.get('domains', []):
        _object(domain, {'id', 'name', 'dimensions'}, 'domain')
        identifier = domain.get('id')
        if not _identifier(identifier) or identifier in domains or not isinstance(domain.get('name'), str):
            raise ValueError('Domains require unique identifiers and names')
        if not isinstance(domain.get('dimensions'), list) or not domain['dimensions'] or not set(domain['dimensions']) <= dimensions:
            raise ValueError('Domains require registered physical dimensions')
        domains[identifier] = domain
    roles = {}
    for role in record.get('roles', []):
        _object(role, {'id', 'name', 'domain', 'structures', 'dimensions', 'operations'}, 'role')
        identifier = role.get('id')
        if not _identifier(identifier) or identifier in roles or not isinstance(role.get('name'), str):
            raise ValueError('Roles require unique identifiers and names')
        if role.get('domain') not in domains:
            raise ValueError('Role domain is not declared')
        structures = role.get('structures')
        role_dimensions = role.get('dimensions')
        if not isinstance(structures, list) or not structures or not set(structures) <= STRUCTURES:
            raise ValueError('Role requires supported structures')
        if not isinstance(role_dimensions, list) or not role_dimensions or not set(role_dimensions) <= set(domains[role['domain']]['dimensions']):
            raise ValueError('Role dimensions must be declared by its domain')
        if not isinstance(role.get('operations', []), list):
            raise ValueError('Role operations must be an array')
        for op in role.get('operations', []):
            if op not in OPERATION_CAPABILITIES or not set(structures) & set(OPERATION_CAPABILITIES[op]['structures']):
                raise ValueError('Unsupported operation for custom role: ' + str(op))
        roles[identifier] = role
    channels = {}
    for channel in record.get('channels', []):
        _object(channel, {'id', 'name', 'aliases', 'patterns', 'mapping', 'domain', 'unit', 'data_type', 'calibration'}, 'channel')
        identifier = channel.get('id')
        if not _identifier(identifier) or identifier in channels or not isinstance(channel.get('name'), str):
            raise ValueError('Channels require unique identifiers and names')
        if not isinstance(channel.get('aliases', []), list) or any(not isinstance(v, str) for v in channel.get('aliases', [])):
            raise ValueError('Channel aliases must be strings')
        if not isinstance(channel.get('patterns', []), list):
            raise ValueError('Channel patterns must be an array')
        for pattern in channel.get('patterns', []):
            if (not isinstance(pattern, str) or len(pattern) > 120 or not pattern.startswith('^') or not pattern.endswith('$')
                    or re.search(r'[^a-zA-Z0-9_ ^$.*?\[\]\\-]', pattern) or '**' in pattern or pattern.count('*') + pattern.count('?') > 2):
                raise ValueError('Use short anchored literal/character-class patterns')
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError('Invalid profile recognition pattern') from exc
        mapping = validate_mapping(channel.get('mapping', {}))
        role = roles.get(mapping['role'])
        if not role or mapping['structure'] not in role['structures'] or mapping['domain'] != role['domain']:
            raise ValueError('Channel mapping must implement a declared role')
        if mapping['dimension'] not in role['dimensions'] or unit(mapping['unit']) not in UNITS or UNITS[unit(mapping['unit'])][0] != mapping['dimension']:
            raise ValueError('Channel dimension does not match its role/unit')
        channels[identifier] = (channel, mapping)
    operation_declarations = record.get('operations', [])
    if not isinstance(operation_declarations, list):
        raise ValueError('Operations must be an array')
    for operation in operation_declarations:
        _object(operation, {'id', 'version'}, 'operation declaration')
        if operation.get('id') not in OPERATION_CAPABILITIES or str(operation.get('version', '1')) != OPERATION_CAPABILITIES[operation['id']]['version']:
            raise ValueError('Unknown profile operation or incompatible implementation version')
    ids = set()
    for kpi in record.get('kpis', []):
        _object(kpi, {'id', 'name', 'channel', 'op', 'unit', 'group', 'other_channel', 'phase', 'allow_any_time', 'calibration', 'scale', 'parameters'}, 'KPI')
        if not isinstance(kpi.get('id'), str) or kpi['id'] in ids or kpi.get('channel') not in channels:
            raise ValueError('KPI requires a unique identifier and channel')
        ids.add(kpi['id'])
        definition, mapping = channels[kpi['channel']]
        role = roles[mapping['role']]
        operation = kpi.get('op')
        if operation not in OPERATION_CAPABILITIES or operation not in role['operations'] or mapping['structure'] not in OPERATION_CAPABILITIES[operation]['structures']:
            raise ValueError('KPI operation is incompatible with its channel capability')
        if unit(kpi.get('unit', '')) not in UNITS:
            raise ValueError('Unknown KPI output unit')
        if operation in ('difference', 'ratio') and kpi.get('other_channel') not in channels:
            raise ValueError('KPI requires a compatible second channel')
        source_dimension = mapping['dimension']
        output_dimension = UNITS[unit(kpi.get('unit', ''))][0]
        if operation in ('mean', 'max', 'min', 'std', 'rms', 'first', 'last', 'absmax', 'difference', 'counter') and output_dimension != source_dimension:
            raise ValueError('KPI output dimension must match its input')
        if operation in ('duration', 'on_duration') and output_dimension != 'time':
            raise ValueError('Duration KPI output must be time')
        if operation == 'ratio' and output_dimension != 'ratio':
            raise ValueError('Ratio KPI output must be dimensionless')
        if operation in ('difference', 'ratio') and channels[kpi['other_channel']][1]['dimension'] != source_dimension:
            raise ValueError('Difference/ratio input dimensions must agree')
        if operation == 'integral' and {'flow': 'volume', 'power': 'energy'}.get(source_dimension) != output_dimension:
            raise ValueError('Integral KPI requires a registered integrated dimension')
        if operation == 'pulse_volume' and output_dimension != 'volume':
            raise ValueError('Pulse-volume KPI requires a volume output')
    # Reuse the existing bounded conditions/calibration/acceptance validation.
    # Custom domain/role names are deliberately absent from that old validator.
    from app_appliance_profiles import validate_condition, validate_details
    for phase in record.get('phases', []):
        _object(phase, {'name', 'conditions', 'minimum_seconds', 'debounce_seconds'}, 'phase')
        if not phase.get('name') or not isinstance(phase.get('conditions', []), list):
            raise ValueError('Invalid profile phase')
        for condition in phase.get('conditions', []):
            validate_condition(condition, set(channels))
    for metric_id, rule in record.get('acceptance', {}).items():
        _object(rule, {'min', 'max', 'unit'}, 'acceptance')
        if metric_id not in ids or not ({'min', 'max'} & set(rule)):
            raise ValueError('Acceptance requires a known KPI and explicit limit')
    for channel_id, rule in record.get('tolerances', {}).items():
        _object(rule, {'relative_percent', 'absolute', 'unit', 'times_s', 'lower', 'upper', 'uncertainty'}, 'tolerance')
        if channel_id not in channels:
            raise ValueError('Tolerance channel is not declared')
    validate_details(record)
    result = copy.deepcopy(record)
    # Keep the established engineering profile consumer compatible while the
    # schema-2 mapping remains the source of typed meaning for the new workflow.
    for channel in result.get('channels', []):
        mapping = channels[channel['id']][1]
        channel['mapping'] = mapping
        channel.setdefault('unit', mapping['unit'])
        channel.setdefault('domain', mapping['domain'])
        channel.setdefault('data_type', {'binary': 'state', 'enum': 'code', 'counter': 'count'}.get(mapping['structure'], 'analog'))
        if channel['unit'] != mapping['unit'] or channel['domain'] != mapping['domain']:
            raise ValueError('Legacy channel fields must agree with the typed mapping')
    return strict_json(result)


def profile_v2(record):
    """Explicit adapter; schema-1 source profiles and workspaces are unchanged.

    Legacy aliases carry suggestions rather than confirming acquisition/scaling.
    This adapter never turns schema-1 code channels into physical binary states.
    """
    if record.get('schema_version') == 2:
        return validate_profile_v2(record)
    from app_appliance_profiles import validate_profile
    legacy = validate_profile(record)
    result = copy.deepcopy(legacy)
    result.update(schema_version=2, domains=[], roles=[], operations=[],
        migration={'source_schema_version': 1, 'semantics': 'Legacy recognition retained as review suggestions'})
    dimensions_by_domain = {}
    for channel in legacy['channels']:
        dimension = UNITS[unit(channel['unit'])][0]
        dimensions_by_domain.setdefault(channel['domain'], set()).add(dimension)
    result['domains'] = [{'id': key, 'name': key.replace('_', ' ').title(), 'dimensions': sorted(value)} for key, value in dimensions_by_domain.items()]
    type_map = {'analog': 'analog', 'state': 'binary', 'code': 'enum', 'count': 'counter'}
    for channel in result['channels']:
        structure = type_map[channel['data_type']]
        # Legacy counter KPI definitions often use analog channels. Preserve them
        # as requested definitions without asserting a counter interpretation.
        role_operations = [op for op, definition in OPERATION_CAPABILITIES.items() if structure in definition['structures']]
        result['roles'].append({'id': channel['id'], 'name': channel['name'], 'domain': channel['domain'],
            'structures': [structure], 'dimensions': [UNITS[unit(channel['unit'])][0]], 'operations': role_operations})
        channel['mapping'] = {'schema_version': 2, 'structure': structure, 'role': channel['id'],
            'domain': channel['domain'], 'unit': channel['unit'], 'dimension': UNITS[unit(channel['unit'])][0],
            'authority': {'kind': 'heuristic', 'source': 'schema-1 adapter', 'version': '1', 'reviewed': False}}
    # Retain legacy KPI requests in migration provenance when their historical
    # structure was insufficiently explicit for the schema-2 operation contract.
    result['migration']['unresolved_kpis'] = [k for k in result.get('kpis', []) if k['op'] not in next(r['operations'] for r in result['roles'] if r['id'] == k['channel'])]
    result['kpis'] = [k for k in result.get('kpis', []) if k not in result['migration']['unresolved_kpis']]
    valid_ids = {k['id'] for k in result['kpis']}
    result['acceptance'] = {k: v for k, v in result.get('acceptance', {}).items() if k in valid_ids}
    return validate_profile_v2(result)
