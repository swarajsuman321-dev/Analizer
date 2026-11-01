"""Example trusted analyser: unweighted native-sample median absolute deviation."""
import numpy as np
from app_parameter_capabilities import CapabilityDefinition


def _analyse(projection, context):
    context.check()
    values = context.y[context.finite]
    value = float(np.median(np.abs(values - np.median(values)))) if len(values) else None
    context.emit('example.native_mad', value,
        weighting='unweighted original valid observations; sampling-density dependent',
        evidence_basis='descriptive native-sample measurement')


def register_patch(manager):
    manager.register_analyser(CapabilityDefinition(
        'example.native_mad', definition_version='1',
        structures=('analog', 'quantized_analog', 'setpoint', 'unknown'),
        required_inputs=('values',), prerequisites=('scalar numeric observations',),
        coverage_policy='valid native observations only; no interpolation or timing claim',
        description='Native-sample median absolute deviation; no normal-distribution scaling'), _analyse)
