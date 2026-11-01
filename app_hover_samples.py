"""Native hover observations with explicit missing/support information.

The pointer is a requested coordinate, not a source observation. A hover record
therefore keeps both the requested coordinate and actual nearest sample time.
No interpolated measurement or extrapolated endpoint is presented as a sample.
"""
import numpy as np

from app_cursor_identity import nearest_index


def hover_sample(channel, point, cache=None):
    """Return a real row or an explicit unavailable reason at ``point``.

    Missing samples stay missing and long acquisition gaps do not borrow a
    measurement from a distant boundary. The fallback gap limit is disclosed
    and matches the existing Trace policy (3 × median positive interval).
    """
    x, y = channel.values()
    record = {'channel': channel.id, 'requested_x': float(point), 'index': None,
              'x': None, 'y': None, 'unit': channel.unit,
              'coordinate_unit': channel.coordinate_unit, 'available': False,
              'reason': '', 'gap_policy': ''}
    if not len(x):
        record['reason'] = 'No recorded samples'
        return record
    if not np.isfinite(point) or point < x[0] or point > x[-1]:
        record['reason'] = 'Outside recorded support'
        return record
    key = (channel.id, channel.revision, id(x))
    details = (cache or {}).get(key)
    if details is None:
        policy = channel.attributes.get('acquisition_policy') or {}
        if not isinstance(policy, dict):
            policy = {'mode': policy}
        limit = policy.get('max_gap_seconds', policy.get('max_gap_s', channel.attributes.get('max_gap_seconds')))
        if limit is not None and channel.coordinate_kind == 'time':
            from app_time_units import minute_factor
            try:
                limit = float(limit)/(minute_factor(channel.coordinate_unit)*60)
            except (ValueError,TypeError,OverflowError):
                record['reason']='Invalid configured acquisition gap policy'
                return record
            if not np.isfinite(limit) or limit<0:
                record['reason']='Invalid configured acquisition gap policy'
                return record
            description = 'Configured maximum supported gap'
        elif policy.get('mode') in ('event', 'event_log', 'exact_event_log'):
            limit, description = np.inf, 'Declared event log; no waveform dropout inferred'
        else:
            differences = np.diff(x)
            positive = differences[differences > 0]
            limit = 3*float(np.median(positive)) if len(positive) else 0.
            description = 'Conservative fallback: 3 × median positive sample interval'
        details = limit, description
        if cache is not None:
            cache[key] = details
    limit, record['gap_policy'] = details
    index = nearest_index(x, point)
    record.update(index=int(index), x=float(x[index]))
    # Exact source times remain inspectable, including a lone observation.
    if x[index] != point:
        left = int(np.searchsorted(x, point, side='right')-1)
        right = left+1
        if left < 0 or right >= len(x) or x[right]-x[left] > limit:
            record['reason'] = 'Acquisition gap: no supported sample at this time'
            return record
        if not np.isfinite(y[left]) or not np.isfinite(y[right]):
            record['reason'] = 'Missing or invalid observation around this time'
            return record
    if not np.isfinite(y[index]):
        record['reason'] = 'Recorded value is missing or invalid'
        return record
    record.update(y=float(y[index]), available=True)
    return record


def compatible_hover_coordinate(source, target, point):
    """Convert a common pointer coordinate without rebasing any recording."""
    if source is None or target is None or source[0] != target[0]:
        return None
    if source == target:
        return float(point)
    if source[0] != 'time':
        return None
    from app_time_units import minute_factor
    try:
        return float(point)*minute_factor(source[1])/minute_factor(target[1])
    except ValueError:
        return None
