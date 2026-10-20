"""Bounded report presentation; complete events remain separate evidence.

Grouping is a view over original records. It never deletes, joins or changes the
measurements in the detailed event log. The grouping key and interval-union
policy are exported so an engineer can reproduce every displayed total.
"""
from collections import defaultdict
import hashlib
import json
import math


GROUPING_POLICY = ('Run + report scope + category + rule name/type + source channel + '
                   'evaluation status + effective rule; overlapping intervals are '
                   'united only for affected-time summary, never in the source log')


def finite_number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def event_category(record):
    if record.get('category'):
        return record['category']
    if record.get('type') == 'dropout' or record.get('name') == 'Data quality limitation':
        return 'Data Quality'
    if str(record.get('status', '')).lower() == 'not evaluated':
        return 'Rule Evaluation'
    return 'Appliance Event'


def event_identity(record, run, index):
    """Stable within a run, including equal observations at the same timestamp."""
    payload = json.dumps([run.get('dataset_id'), run.get('role', 'analysis'),
                          run.get('report_scope', 'whole_recording'), index,
                          record.get('event_id') or record], sort_keys=True, ensure_ascii=False, default=str)
    return 'event-' + hashlib.sha256(payload.encode()).hexdigest()[:20]


def union_duration(intervals):
    """Return elapsed seconds in the union, without double-counting overlap."""
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end-start for start, end in merged)


def summarize_events(records):
    groups = defaultdict(list)
    for record in records:
        evidence = record.get('evidence', {})
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except (TypeError, ValueError):
                evidence = {'note': evidence}
        rule = {'definition':record.get('rule', evidence),
                'gap_threshold_s':record.get('gap_threshold_s'),
                'acquisition_policy':record.get('acquisition_policy')}
        # Warnings have no timing rule; group their category while keeping every
        # original warning and its text in the evidence package.
        rule_key = json.dumps(rule, sort_keys=True, default=str) if record.get('type') else ''
        key = (record.get('Run', 'Analysis'), record.get('Scope', 'Whole recording'),
               event_category(record), record.get('name', 'Evaluation note'),
               record.get('type', ''), record.get('channel_id', evidence.get('channel', '')),
               record.get('status', 'Not evaluated'), rule_key)
        groups[key].append(record)
    result = []
    for key, rows in groups.items():
        intervals = []
        for row in rows:
            start, end = finite_number(row.get('start_s')), finite_number(row.get('end_s'))
            if start is not None and end is not None and end >= start:
                intervals.append((start, end))
        first = min((a for a, _ in intervals), default=None)
        last = max((b for _, b in intervals), default=None)
        longest = max((b-a for a, b in intervals), default=None)
        group_id = 'group-' + hashlib.sha256(json.dumps(key, default=str).encode()).hexdigest()[:16]
        result.append({'group_id': group_id, 'Run': key[0], 'Scope': key[1],
                       'category': key[2], 'name': key[3], 'type': key[4],
                       'channel': key[5], 'status': key[6], 'count': len(rows),
                       'effective_rule': key[7],
                       'effective_gap_threshold_s':rows[0].get('gap_threshold_s'),
                       'affected_time_union_s': union_duration(intervals) if intervals else None,
                       'longest_interval_s': longest, 'first_s': first, 'last_s': last,
                       'representative_ids': [r['event_id'] for r in sorted(rows, key=lambda r: -(finite_number(r.get('duration_s')) or 0))[:3]],
                       'event_ids': [r['event_id'] for r in rows],
                       'grouping_policy': GROUPING_POLICY})
    return sorted(result, key=lambda r: (-r['count'], r['category'], r['name']))


SCOPE_LABELS = {'whole_recording': 'Whole recording',
                'cursor_interval': 'Active cursor interval',
                'both': 'Whole recording and active cursor interval'}


def scope_label(run):
    return SCOPE_LABELS.get(run.get('report_scope', 'whole_recording'), 'Whole recording')


def required_result(result,profile):
    """Primary results and configured acceptance decisions stay in the PDF."""
    definition=result.get('definition',result)
    return bool(definition.get('mandatory') or definition.get('primary') or result.get('id') in profile.get('acceptance',{}))


def report_plan(runs, *, scope='whole_recording', detailed_appendix=False):
    """Exact page plan shared by preview and renderer.

    The default ten-page summary has a declared presentation budget, not a data limit.
    Event growth cannot expand it. Detailed evidence always retains all rows;
    only an explicitly requested appendix adds one page per 20 full log records.
    """
    if scope not in SCOPE_LABELS:
        raise ValueError('Choose whole recording, active cursor interval or both')
    events = sum(len(run.get('anomalies', [])) + len(run.get('warnings', [])) for run in runs)
    mandatory=sum(required_result(result,run['profile']) for run in runs for result in run.get('kpis',[]))
    continuation_pages=math.ceil(max(0,mandatory-18)/8)
    sections = [
        {'title': '1. Purpose, readiness and source quality', 'first_page': 1, 'pages': 2},
        {'title': '2. Phase timeline and graphical evidence', 'first_page': 3, 'pages': 3},
        {'title': '3. Engineering results and comparison', 'first_page': 6, 'pages': 2+continuation_pages},
        {'title': '4. Events, conclusions and traceability', 'first_page': 8+continuation_pages, 'pages': 3},
    ]
    appendix_pages = math.ceil(events/20) if detailed_appendix else 0
    return {'expected_pages': 10 + continuation_pages + appendix_pages, 'summary_pages': 10+continuation_pages,
            'required_result_records':mandatory,'result_continuation_pages':continuation_pages,
            'appendix_pages': appendix_pages, 'section_pages': sections,
            'scope': scope, 'scope_label': SCOPE_LABELS[scope],
            'event_records': events, 'detailed_appendix': bool(detailed_appendix),
            'event_grouping_policy': GROUPING_POLICY,
            'companion_evidence': 'Every KPI, event, mapping and full configuration is retained in Excel, events CSV and JSON beside the PDF.'}
