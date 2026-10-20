"""Actionable input checks shared by processing controls and acceptance tests."""
import numpy as np
from app_signal_processing import strict_clock

SPECTRAL = {'Butterworth low-pass', 'FFT', 'Welch PSD'}


def processing_preflight(channel, operation, cutoff=None):
    """Describe prerequisites without resampling or assigning physical meaning."""
    if channel is None:
        return {'valid': False, 'message': 'Select one source channel in the Data Portal.', 'nyquist': None}
    physical = channel.unit or 'Unknown physical unit'
    result = {'valid': True, 'message': f'Source: {channel.name} · {physical}.', 'nyquist': None}
    if operation in SPECTRAL:
        if channel.coordinate_kind != 'time':
            result.update(valid=False, message='Select a time-based channel. Frequency in Hz requires a known time clock.')
            return result
        try:
            _, _, seconds = strict_clock(channel)
        except ValueError as exc:
            result.update(valid=False, message=str(exc) + '. Use Resampling with an explicit step; missing support remains unknown.')
            return result
        nyquist = .5 / seconds
        result['nyquist'] = nyquist
        result['message'] = f'Sample rate {1 / seconds:.6g} Hz · Nyquist {nyquist:.6g} Hz · {physical}.'
        if operation == 'Butterworth low-pass':
            result['message'] += f' Choose 0 < cutoff < {nyquist:.6g} Hz.'
            if cutoff is not None and (not np.isfinite(cutoff) or not 0 < cutoff < nyquist):
                result['valid'] = False
    if not channel.unit and operation in ('Differentiation', 'Cumulative integration'):
        result['message'] += ' Result has an unknown physical quantity; confirm the source unit before reporting engineering totals.'
    return result
