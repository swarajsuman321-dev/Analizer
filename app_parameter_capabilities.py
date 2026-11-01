"""Small, explicit registries for trusted numerical extensions.

Profiles contain capability identifiers and parameters only. A callable can enter
this registry only through application code or an installed trusted Python patch;
names found in source files or profile JSON are never imported or evaluated.
"""
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from collections.abc import Mapping
import re

from app_parameter_contracts import STRUCTURES, strict_json


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key:_freeze(item) for key,item in value.items()})
    if isinstance(value,list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if isinstance(value,Mapping):
        return {key:_thaw(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    definition_version: str = '1'
    structures: tuple = ()
    roles: tuple = ()
    dimensions: tuple = ()
    required_inputs: tuple = ('values',)
    parameters: dict = field(default_factory=dict)
    prerequisites: tuple = ()
    scopes: tuple = ('run', 'stage')
    output_units: tuple = ('source',)
    evidence_requirements: tuple = ()
    coverage_policy: str = 'original observations; no extrapolation'
    description: str = ''

    def __post_init__(self):
        if not isinstance(self.capability_id, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', self.capability_id):
            raise ValueError('A capability needs a stable alphanumeric identifier')
        if not isinstance(self.definition_version, str) or not self.definition_version.strip():
            raise ValueError('A capability needs an implementation version')
        for name in ('structures', 'roles', 'dimensions', 'required_inputs', 'prerequisites',
                     'scopes', 'output_units', 'evidence_requirements'):
            items = getattr(self, name)
            if not isinstance(items, (tuple, list)) or any(not isinstance(v, str) or not v for v in items):
                raise ValueError(name + ' must contain nonempty strings')
            object.__setattr__(self, name, tuple(items))
        if set(self.structures) - STRUCTURES:
            raise ValueError('Capability advertises unsupported structures')
        if not self.required_inputs or not self.scopes or not self.output_units:
            raise ValueError('Capabilities must declare inputs, scopes and output units')
        if not isinstance(self.parameters, dict):
            raise ValueError('Capability parameters must be declarative metadata')
        object.__setattr__(self, 'parameters', _freeze(strict_json(self.parameters)))
        if not isinstance(self.coverage_policy, str) or not self.coverage_policy.strip():
            raise ValueError('A capability must declare its coverage policy')

    def metadata(self):
        return strict_json({item.name:_thaw(getattr(self,item.name)) for item in fields(self)})


class CapabilityRegistry:
    """Insertion-ordered definitions with transactional extension snapshots."""
    def __init__(self):
        self._entries = {}

    def register(self, definition, analyser, *, trusted=False):
        if not trusted:
            raise ValueError('Only trusted application/plugin code may register an analyser')
        if isinstance(definition, dict):
            definition = CapabilityDefinition(**definition)
        if not isinstance(definition, CapabilityDefinition) or not callable(analyser):
            raise TypeError('An analyser needs validated capability metadata and a callable')
        if definition.capability_id in self._entries:
            raise ValueError('Capability already registered: ' + definition.capability_id)
        self._entries[definition.capability_id] = (definition, analyser)
        return definition

    def definitions(self):
        return [definition.metadata() for definition, _ in self._entries.values()]

    def entries(self):
        return tuple(self._entries.values())

    def clone(self):
        result = CapabilityRegistry()
        result._entries.update(self._entries)
        return result

    def snapshot(self):
        return dict(self._entries)

    def restore(self, snapshot):
        self._entries.clear()
        self._entries.update(snapshot)

    def validate_extension(self, before):
        for key, entry in before.items():
            if key not in self._entries or self._entries[key] is not entry:
                raise ValueError('A plugin cannot remove or overwrite another capability: ' + key)
        for key, (definition, analyser) in self._entries.items():
            if not isinstance(definition, CapabilityDefinition) or key != definition.capability_id or not callable(analyser):
                raise ValueError('Invalid analyser registration')

    def applicable(self, projection):
        from app_engineering_units import UNITS, unit
        dimension = UNITS.get(unit(projection.get('unit', '')), ('unknown',))[0]
        for definition, analyser in self._entries.values():
            if definition.structures and projection.get('structure', 'unknown') not in definition.structures:
                continue
            if definition.roles and projection.get('role', '') not in definition.roles:
                continue
            if definition.dimensions and dimension not in definition.dimensions:
                continue
            yield definition, analyser
