"""Executable acceptance checks shared by source and all Windows editions.

The application itself imports this module for ``--acceptance-check``.  A test
runner cannot substitute a Python stub for the frozen workbench: the result
records the executable, frozen status, edition and actual Qt platform.  Physical
DPI, graphics drivers, accessibility and manual mouse checks remain explicitly
unrun; offscreen geometry is not evidence for those claims.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import sys
import time
import traceback
import uuid


MANUAL_WINDOWS_CHECKS = [
    'Physical wheel, box selection and keyboard navigation in every zoom mode',
    'Windows 100%, 125%, 150% and 200% display scaling',
    'Moving between monitors with different scaling and graphics drivers',
    'Keyboard-only task completion and screen-reader announcements',
    'Long-running acquisition-sized workloads and antivirus policy interaction',
]

# This finite contract inventory prevents a green but accidentally shortened
# runner from satisfying a release gate simply by retaining its category labels.
# New checks may be added without weakening any of the already approved ones.
REQUIRED_CHECK_IDS = frozenset({
    'REAL-FIXTURE-INTEGRITY-IMPORT', 'ALL-15-FILE-COMBINATIONS',
    'PER-FILE-CHECKBOX-AND-CLOSE-DATASET', 'TDMS-FIRST-REVIEW-REUSE-UNKNOWN-ONLY',
    'SYNTHETIC-SOURCE-EDGE-CASES', 'LOCKED-SAMPLE-MARKER-HUD-EXPORT-RESTORE',
    'GRAPH-HEADER-CONTEXT-SAFE-NATIVE-FFT', 'NON-TEMPORAL-AND-UNLOCKED-INDEPENDENCE',
    'NUMERICAL-UNITS-AND-SAFETY-REJECTIONS',
    'PROCESSING-PREFLIGHT-VALID-DEFAULT-AND-EXPLANATIONS',
    'QT-WHEEL-BOX-KEYBOARD-SHARED-MODES',
    'EXACT-REAL-SOURCE-WORKSPACE-ROUNDTRIP',
    'REAL-INTERVAL-EXPORT-FORMATS-AND-AGREEMENT', 'SOURCE-FILES-UNCHANGED',
} | {f'LAYOUT-{layout}-{theme}-{width}'
     for layout in ('Single', 'Horizontal split', 'Vertical split', '2×2', 'Stacked', '3 stacked', '10 panels')
     for theme in ('Dark', 'Light') for width in (1024, 1536)})


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def viewport_time_x(pane, value):
    """Map a timestamp through the complete floating viewport transform.

    Each plot owns its own scene.  Comparing scene coordinates, or rounding with
    mapFromScene(), can miss different canvas gutters at the same numeric time.
    Qt returns logical pixels here; this is not physical-DPI certification.
    """
    from PySide6 import QtCore
    point = pane.getViewBox().mapViewToScene(QtCore.QPointF(float(value), 0))
    viewport = pane.viewportTransform().map(point)
    return float(pane.viewport().mapToGlobal(QtCore.QPoint(0, 0)).x()+viewport.x())


def time_pixel_alignment(panes, columns, *, tolerance=.5):
    """Assert equal numeric time bounds also draw at equal X pixels per column."""
    import numpy as np
    assert columns > 0
    groups = {}
    for index, pane in enumerate(panes):
        if pane.ids and pane.coordinate and pane.coordinate[0] == 'time':
            groups.setdefault((index % columns, tuple(pane.coordinate)), []).append((index, pane))
    observed = []
    for (column, coordinate), members in groups.items():
        first = members[0][1]
        bounds = np.asarray(first.getViewBox().viewRange()[0], dtype=float)
        timestamps = [float(bounds[0]+(bounds[1]-bounds[0])*fraction) for fraction in (0, .1, .5, .9, 1)]
        records = []
        for index, pane in members:
            np.testing.assert_allclose(pane.getViewBox().viewRange()[0], bounds, rtol=0, atol=1e-7,
                err_msg='Pixel alignment must preserve identical numeric time limits')
            positions = [viewport_time_x(pane, timestamp) for timestamp in timestamps]
            assert np.isfinite(positions).all() and positions[-1] > positions[0], 'Invalid time-to-viewport transform'
            records.append({'pane_index': index, 'time_pixel_x': positions,
                            'axis_units': list(dict.fromkeys(pane.bindings.values()))})
        pixels = np.asarray([record['time_pixel_x'] for record in records])
        spreads = np.ptp(pixels, axis=0)
        assert np.all(spreads <= tolerance+1e-7), (
            f'Common timestamps differ by {spreads.tolist()} logical pixels in grid column {column}; '
            f'numeric bounds agree but the drawing gutters do not (limit {tolerance})')
        observed.append({'column': column, 'coordinate': list(coordinate), 'numeric_bounds': bounds.tolist(),
                         'timestamps': timestamps, 'maximum_pixel_spread': float(spreads.max()),
                         'tolerance_logical_pixels': tolerance, 'panes': records})
    assert observed, 'No temporal pane was available for pixel-alignment acceptance'
    return observed


@contextmanager
def isolated_environment(output):
    """Keep diagnostics away from a user's templates, outputs and settings."""
    overrides = {'ANALIZER_SETTINGS_DIR': str(output/'settings'),
                 'ANALIZER_OUTPUT_DIR': str(output/'outputs'),
                 'MPLCONFIGDIR': str(output/'matplotlib'),
                 'XDG_CACHE_HOME': str(output/'cache'),
                 'QT_QPA_PLATFORM': os.environ.get('QT_QPA_PLATFORM', 'offscreen')}
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class AcceptanceRecorder:
    """Persist completed checks even when a later application callback fails."""
    def __init__(self, path, metadata=None):
        self.path = Path(path)
        self.result = {**(metadata or {}), 'checks': [], 'callback_errors': [],
                       'runner_errors': [], 'expected_safety_rejections': [],
                       'manual_checks_unrun': list(MANUAL_WINDOWS_CHECKS)}
        self.current = 'startup'

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.result, indent=2, ensure_ascii=False,
                                       default=str)+'\n', encoding='utf-8')

    def check(self, name, operation, category, requires=()):
        self.current = name
        started = time.perf_counter()
        complete = {row['id']: row['status'] for row in self.result['checks']}
        blockers = [dependency for dependency in requires if complete.get(dependency) != 'passed']
        if blockers:
            row = {'id': name, 'category': category, 'status': 'unrun',
                   'blocked_by': blockers, 'seconds': 0}
            self.result['checks'].append(row)
            self.save()
            return row
        try:
            observed = operation()
            row = {'id': name, 'category': category, 'status': 'passed',
                   'observed': observed}
        except AssertionError:
            row = {'id': name, 'category': category, 'status': 'unmet',
                   'error': traceback.format_exc()}
        except Exception:
            error = {'id': name, 'category': category, 'error': traceback.format_exc()}
            self.result['runner_errors'].append(error)
            row = {'id': name, 'category': category, 'status': 'execution_error',
                   'error': error['error']}
        row['seconds'] = round(time.perf_counter()-started, 3)
        self.result['checks'].append(row)
        self.save()
        return row

    def finish(self, required_checks=()):
        present = {row['id'] for row in self.result['checks']}
        for missing in sorted(set(required_checks)-present):
            self.result['checks'].append({'id': missing, 'category': 'coverage',
                'status': 'unrun', 'seconds': 0,
                'reason': 'The required acceptance contract did not execute'})
        rows = self.result['checks']
        self.result['summary'] = {
            'checks': len(rows), 'passed': sum(r['status'] == 'passed' for r in rows),
            'unmet': sum(r['status'] == 'unmet' for r in rows),
            'unrun': sum(r['status'] == 'unrun' for r in rows),
            'runner_errors': len(self.result['runner_errors']),
            'application_callback_errors': len(self.result['callback_errors']),
            'expected_safety_rejections': len(self.result['expected_safety_rejections']),
            'manual_unrun': len(self.result['manual_checks_unrun'])}
        self.result['ok'] = bool(rows) and all(r['status'] == 'passed' for r in rows) and not (
            self.result['callback_errors'] or self.result['runner_errors'])
        self.result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        self.save()
        return self.result


def run_acceptance(samples, output):
    """Exercise the real workbench; return a JSON-compatible finite test report.

    ``samples`` is an external directory containing the four committed recording
    fixtures and manifest.  Test recordings are deliberately not bundled into
    application distributions.  Missing or changed fixtures fail the gate.
    ``output`` must be a disposable diagnostic directory, never a user workspace.
    """
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # No display server is necessary on the native CI runner.  A caller can
    # deliberately select a real platform plugin for separate visual checks.
    from app_version import VERSION
    from app_installation import installed_root
    frozen = bool(getattr(sys, 'frozen', False))
    installed = bool(installed_root())
    distribution_form = ('source' if not frozen else 'installed' if installed else
                         'standalone-folder' if (Path(sys.executable).parent/'_internal').is_dir()
                         else 'standalone-onefile')
    recorder = AcceptanceRecorder(output/'acceptance.json', {
        'schema': 1, 'version': VERSION, 'platform': sys.platform,
        'run_id': os.environ.get('ANALIZER_ACCEPTANCE_RUN_ID') or str(uuid.uuid4()),
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'frozen': frozen, 'executable': str(Path(sys.executable).resolve()),
        'edition': 'source' if not frozen else 'installed' if installed else 'standalone',
        'distribution_form': distribution_form,
        'qt_platform_requested': os.environ.get('QT_QPA_PLATFORM', 'offscreen'), 'inputs': []})
    with isolated_environment(output):
        _run_workbench(recorder, Path(samples).resolve() if samples else None, output)
    return recorder.finish(required_checks=REQUIRED_CHECK_IDS)


def _run_workbench(recorder, samples, output):
    import numpy as np
    import pandas as pd
    from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    from app_channel_store import Channel, ChannelStore, Dataset
    from app_ingestion import ingest
    from app_plot_workspace import LAYOUTS
    from app_reporting import export_report, interval_tables
    from app_signal_processing import strict_clock, transform, formula
    from app_tdms_templates import ParameterTemplates, ParameterReview, identity
    from app_workbench import AdvancedStudioWindow
    from app_workspace_io import save_workspace, load_workspace

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recorder.result['qt_platform'] = app.platformName()
    old_hook = sys.excepthook
    def callback_error(kind, value, tb):
        recorder.result['callback_errors'].append({'scenario': recorder.current,
            'error': ''.join(traceback.format_exception(kind, value, tb))})
        recorder.save()
    sys.excepthook = callback_error
    window = None
    def events():
        app.processEvents()
        QtTest.QTest.qWait(25)
        app.processEvents()
    try:
        window = AdvancedStudioWindow()
        window.resize(1536, 960)
        window.show()
        events()
        store = window.store
        workspace = window.dashboard
        fixture_stores = {}
        manifest = None

        def load_fixtures():
            nonlocal manifest
            assert samples and (samples/'manifest.json').is_file(), 'The real-fixture manifest is required'
            manifest = json.loads((samples/'manifest.json').read_text(encoding='utf-8'))
            assert len(manifest['files']) == 4, 'Expected the four approved recording fixtures'
            for entry in manifest['files']:
                path = samples/entry['filename']
                assert path.is_file() and path.stat().st_size == entry['bytes'], 'Fixture size mismatch: '+path.name
                assert sha256_file(path) == entry['sha256'], 'Fixture digest mismatch: '+path.name
                other = ChannelStore()
                ingest(other, path)
                assert other.datasets and other.channels, 'No source data imported: '+path.name
                fixture_stores[entry['role']] = other
                recorder.result['inputs'].append({**entry, 'channels': len(other.channels),
                    'source_rows': [len(dataset.frame) for dataset in other.datasets.values()]})
            store.datasets.update({key: value for other in fixture_stores.values() for key, value in other.datasets.items()})
            with store.batch():
                for other in fixture_stores.values():
                    for channel in other.channels.values():
                        store.add(channel)
            events()
            return {'files': len(fixture_stores), 'channels': len(store.channels)}
        recorder.check('REAL-FIXTURE-INTEGRITY-IMPORT', load_fixtures, 'real_recordings')

        def combinations_and_model_removal():
            assert len(fixture_stores) == 4, 'Import must complete before file combinations'
            rows = []
            roles = tuple(fixture_stores)
            for count in range(1, len(roles)+1):
                for group in combinations(roles, count):
                    mixed = ChannelStore()
                    for role in group:
                        mixed.datasets.update(fixture_stores[role].datasets)
                        mixed.channels.update(fixture_stores[role].channels)
                    expected = sum(len(fixture_stores[role].channels) for role in group)
                    assert len(mixed.channels) == expected
                    workspace.set_layout('Single')
                    for pane in workspace.panes:
                        pane.bind([])
                    representatives = [next(iter(fixture_stores[role].channels)) for role in group]
                    workspace.active.bind(representatives)
                    events()
                    assert set(workspace.active.ids) == set(representatives)
                    first = store.channels[representatives[0]]
                    workspace.active.lock_cursor(0, first.id)
                    workspace.active.step_cursor(0, 1)
                    assert workspace.active.measurements(), 'Combination cursor inspection did not produce readouts'
                    workspace.set_visible(representatives, False)
                    assert not any(pane.ids for pane in workspace.visible_panes())
                    workspace.set_visible(representatives, True)
                    events()
                    plotted = {channel_id for pane in workspace.visible_panes() for channel_id in pane.ids}
                    assert plotted == set(representatives), 'Combination deselect/reselect crossed file partitions'
                    for role in group:
                        isolated = ChannelStore()
                        isolated.datasets.update(mixed.datasets)
                        isolated.channels.update(mixed.channels)
                        removed = isolated.remove_datasets(fixture_stores[role].datasets)
                        target = set(fixture_stores[role].channels)
                        assert removed == target, 'Removal crossed a dataset partition'
                        assert set(isolated.channels) == set(mixed.channels)-target
                        for channel_id, channel in isolated.channels.items():
                            assert channel is mixed.channels[channel_id], 'Unrelated channel identity changed'
                    rows.append({'roles': list(group), 'channels': expected, 'isolated_removals': count,
                                 'representative_plot_channels': len(representatives),
                                 'cursor_step_and_deselect_reselect': True})
            assert len(rows) == 15
            return rows
        recorder.check('ALL-15-FILE-COMBINATIONS', combinations_and_model_removal, 'real_recordings',
                       requires=('REAL-FIXTURE-INTEGRITY-IMPORT',))

        def file_selection_and_removal():
            assert len(fixture_stores) == 4
            window.tabs.setCurrentIndex(0)
            workspace.set_layout('Single')
            for pane in workspace.panes:
                pane.bind([])
            window.sync_visibility()
            window.portal.search.clear()
            window.portal.rebuild()
            tree = window.portal.tree
            assert tree.columnCount() == 2, 'Data Portal must contain only Channel and Unit columns'
            headers = [tree.headerItem().text(index) for index in range(tree.columnCount())]
            assert headers == ['Channel', 'Unit'], 'Unexpected Data Portal column or header'
            iterator = QtWidgets.QTreeWidgetItemIterator(tree)
            while iterator.value():
                item = iterator.value()
                assert all(tree.itemWidget(item, column) is None for column in range(tree.columnCount())), 'Inline file-action widgets consume the channel columns'
                iterator += 1
            observed = []
            for role, other in fixture_stores.items():
                ids = set(other.channels)
                dataset_id = next(iter(other.datasets))
                root = window.portal.dataset_roots[dataset_id]
                root.setCheckState(0, QtCore.Qt.CheckState.Checked)
                events()
                plotted = {channel_id for pane in workspace.visible_panes() for channel_id in pane.ids}
                assert plotted == ids, f'{role} Select All plotted other files or missed its own channels'
                root = window.portal.dataset_roots[dataset_id]
                root.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                events()
                assert not any(pane.ids for pane in workspace.visible_panes()), 'Deselect All left orphan traces'
                observed.append({'role': role, 'selected_channels': len(ids)})
            first, second = list(fixture_stores.values())[:2]
            selected = next(iter(first.channels))
            workspace.set_layout('Single')
            workspace.active.bind([selected])
            preserved = store.channels[selected]
            window.drop_recordings(list(second.datasets))
            events()
            assert store.channels[selected] is preserved and selected in workspace.active.ids
            assert not set(second.channels).intersection(store.channels)
            # Re-add the exact untouched source objects for subsequent checks.
            store.datasets.update(second.datasets)
            with store.batch():
                for channel in second.channels.values():
                    store.add(channel)
            return {'files': observed, 'portal_columns': headers, 'inline_item_widgets': 0}
        recorder.check('PER-FILE-CHECKBOX-AND-CLOSE-DATASET', file_selection_and_removal, 'dataset_isolation',
                       requires=('REAL-FIXTURE-INTEGRITY-IMPORT',))

        def tdms_template_lifecycle():
            assert 'tdms' in fixture_stores
            other = fixture_stores['tdms']
            path = output/'templates'/'tdms-parameters.json'
            templates = ParameterTemplates(path)
            unknown = templates.unknown(other)
            assert unknown, 'The first TDMS import must require review'
            review = ParameterReview(unknown, window)
            try:
                entries = review.entries()
            finally:
                review.close()
            templates.save(entries)
            restarted = ParameterTemplates(path)
            assert not restarted.unknown(other), 'A saved TDMS template was not reused'
            probe = next(iter(other.channels.values()))
            from dataclasses import replace
            new = replace(probe, id='acceptance-unknown-tdms', name='New unknown parameter',
                attributes={**probe.attributes, 'tdms_template_key': 'acceptance/new/unknown'})
            mixed = ChannelStore()
            mixed.channels.update(other.channels)
            mixed.add(new)
            assert [channel.id for channel in restarted.unknown(mixed)] == [new.id]
            assert identity(new) not in restarted.entries
            restarted.apply(mixed)
            for channel_id in other.channels:
                np.testing.assert_array_equal(mixed.channels[channel_id].x, other.channels[channel_id].x)
                # Templates retain original readings even for actuator views.
                original = other.channels[channel_id].raw_y
                if original is not None:
                    np.testing.assert_array_equal(mixed.channels[channel_id].raw_y, original)
            return {'reviewed_parameters': len(entries), 'unknown_only_review': 1}
        recorder.check('TDMS-FIRST-REVIEW-REUSE-UNKNOWN-ONLY', tdms_template_lifecycle, 'templates',
                       requires=('REAL-FIXTURE-INTEGRITY-IMPORT',))

        synthetic = []
        def synthetic_sources():
            ds = Dataset('Acceptance edge cases', pd.DataFrame({'time_min': [0., 1., 1., 2., 4.],
                 'reading': [10., 20., 30., np.nan, 50.], 'literal': ['0', '01', '', 'NaN', '004']}))
            store.datasets[ds.id] = ds
            definitions = [
                Channel('Duplicate readings', [0, 1, 1, 2, 4], [10, 20, 30, np.nan, 50],
                    unit='°C', coordinate_unit='min', dataset_id=ds.id),
                Channel('Discrete valve', [0, 1, 1, 2, 4], [0, 1, 0, np.nan, 1],
                    unit='state', kind='discrete', coordinate_unit='min', dataset_id=ds.id),
                Channel('Masked pressure', [0, 1, 1, 2, 4], [100, 200, 250, 300, 500],
                    unit='Pa', coordinate_unit='min', dataset_id=ds.id, masks=[(2, 2)]),
                Channel('Verified power', np.arange(121)/60, np.full(121, 1000.),
                    unit='W', coordinate_unit='min', dataset_id=ds.id, attributes={'match_percent': 93}),
                Channel('Unknown physical unit', np.arange(121)/60, np.ones(121),
                    coordinate_unit='min', dataset_id=ds.id),
            ]
            with store.batch():
                for channel in definitions:
                    synthetic.append(store.add(channel))
            return {'channels': len(synthetic), 'cases': ['duplicates', 'missing', 'masks', 'discrete', 'unknown units']}
        recorder.check('SYNTHETIC-SOURCE-EDGE-CASES', synthetic_sources, 'synthetic')

        def locked_identity():
            assert len(synthetic) == 5
            window.tabs.setCurrentIndex(0)
            workspace.set_layout('Single')
            pane = workspace.active
            observed = []
            for channel in synthetic[:3]:
                pane.bind([channel.id])
                pane.lock_cursor(0, channel.id)
                # Start before the duplicates, then step through both original
                # source rows; assigning a timestamp alone cannot identify them.
                pane.cursor_locks[0]['index'] = 0
                pane.restore_ranges({**pane.state(), 'cursor_locks': [dict(pane.cursor_locks[0]), None]})
                for expected_index in (1, 2, 3, 4):
                    pane.step_cursor(0, 1)
                    events()
                    lock = pane.cursor_locks[0]
                    assert lock['index'] == expected_index, 'Arrow stepping skipped a duplicate source observation'
                    expected = channel.values()[1][expected_index]
                    measured = pane.measurements()[channel.id]['A']
                    assert np.isclose(measured, expected, equal_nan=True), 'Locked readout disagrees with its exact sample'
                    marker_x, marker_y = pane.cursor_markers[0].getData()
                    if np.isfinite(expected):
                        assert len(marker_y) == 1 and np.isclose(marker_y[0], expected), 'Locked marker uses another duplicate row'
                        assert np.isclose(marker_x[0], channel.values()[0][expected_index])
                    else:
                        assert (not pane.cursor_markers[0].isVisible() or not np.isfinite(marker_y).any()), 'A masked or missing sample has a finite visible marker'
                    _, summary = interval_tables(store, workspace.state())
                    assert np.isclose(summary.iloc[0]['A'], expected, equal_nan=True), 'Export endpoint changed sample identity'
                    saved = pane.state()
                    pane.restore(saved)
                    assert pane.cursor_locks[0]['index'] == expected_index
                    assert np.isclose(pane.measurements()[channel.id]['A'], expected, equal_nan=True)
                    window._readouts()
                    if np.isfinite(expected):
                        assert np.isclose(float(window.readout.item(0, 2).text()), expected), 'HUD disagrees with its sample marker'
                    else:
                        assert window.readout.item(0, 2).text() == 'Unknown'
                # Crossing and clamping must retain nonnegative span and valid
                # source indices; no source rows are removed to obtain this.
                pane.cursor_lines[1].setValue(0)
                pane.cursor_lines[0].setValue(1e9)
                events()
                stats = pane.measurements()[channel.id]
                assert stats['ΔX'] >= 0 and 0 <= pane.cursor_locks[0]['index'] < len(channel.x)
                observed.append({'channel': channel.name, 'source_samples': len(channel.x), 'stepped_rows': 4})
            return observed
        recorder.check('LOCKED-SAMPLE-MARKER-HUD-EXPORT-RESTORE', locked_identity, 'cursor_identity',
                       requires=('SYNTHETIC-SOURCE-EDGE-CASES',))

        def header_and_context():
            workspace.set_layout('Vertical split')
            for pane, channel in zip(workspace.visible_panes(), synthetic):
                pane.bind([channel.id])
            events()
            bar = workspace.navigation_bar
            assert bar.parentWidget() is not window, 'Navigation is still mounted in the global toolbar'
            button = bar.widgetForAction(workspace.navigation_actions['in'])
            assert button is not None
            distance = abs(button.mapToGlobal(button.rect().center()).y()-window.tabs.tabBar().mapToGlobal(window.tabs.tabBar().rect().center()).y())
            assert distance <= 16, f'Navigation is {distance} pixels away from the graph tab header'
            bars = [toolbar for toolbar in window.findChildren(QtWidgets.QToolBar)
                    if toolbar.objectName() in ('graphNavigation', 'AnalysisNavigation', 'ComparisonNavigation') and toolbar.isVisible()]
            assert len(bars) == 1, 'Duplicate primary graph navigation bars are visible'
            pane = workspace.visible_panes()[1]
            menu = pane.create_context_menu()
            try:
                labels = [action.text().replace('&', '').lower() for action in menu.actions() if not action.isSeparator()]
                text = '\n'.join(labels)
                for term in ('pan', 'cursor', 'zoom xy', 'zoom x', 'zoom y', 'snap to cycles', 'revert zoom', 'comments', 'copy', 'export'):
                    assert term in text, 'Missing pane context task: '+term
                assert workspace.active is pane, 'Context menu acts on a different pane'
                assert not pane.getPlotItem().ctrl.fftCheck.isEnabled(), 'Unsupported native FFT remains user-accessible'
                # Even a stale programmatic toggle must not raise a Qt callback.
                pane.getPlotItem().ctrl.fftCheck.setChecked(True)
                pane.getPlotItem().ctrl.fftCheck.setChecked(False)
                events()
            finally:
                menu.close()
            return {'header_center_difference': distance, 'visible_navigation_bars': len(bars), 'context_actions': labels}
        recorder.check('GRAPH-HEADER-CONTEXT-SAFE-NATIVE-FFT', header_and_context, 'navigation',
                       requires=('SYNTHETIC-SOURCE-EDGE-CASES',))

        def assert_ranges(expected=None):
            panes = [pane for pane in workspace.visible_panes() if pane.coordinate == ('time', 'min') and pane.ids]
            assert panes
            ranges = [np.asarray(pane.getViewBox().viewRange()[0]) for pane in panes]
            expected = ranges[0] if expected is None else np.asarray(expected)
            for bounds in ranges:
                np.testing.assert_allclose(bounds, expected, rtol=0, atol=1e-7,
                    err_msg='Lock Time Axes numeric endpoints diverged')
            return [bounds.tolist() for bounds in ranges]

        def layout_theme_geometry(layout, theme, size):
            window.resize(*size)
            window.theme.apply(theme)
            workspace.set_layout(layout)
            _, columns = LAYOUTS[layout]
            real_temperature = next((channel for channel in fixture_stores.get('tdms', ChannelStore()).channels.values()
                if channel.coordinate_kind == 'time' and channel.coordinate_unit == 'min' and channel.unit == '°C'), synthetic[0])
            real_pressure = next((channel for channel in fixture_stores.get('machine', ChannelStore()).channels.values()
                if channel.coordinate_kind == 'time' and channel.coordinate_unit == 'min' and channel.unit == 'Pa'), synthetic[2])
            for index, pane in enumerate(workspace.visible_panes()):
                row, column = divmod(index, columns)
                # In stacked/grid layouts every column contains both narrow
                # single-unit and wide independent multi-unit axis gutters.
                ids = [real_temperature.id] if (row+column) % 2 == 0 else [real_pressure.id, synthetic[3].id, synthetic[1].id]
                pane.bind(ids)

            def settle_painted_axes():
                previous = None
                stable = 0
                for attempt in range(12):
                    app.processEvents()
                    # Offscreen scroll children may not paint with the window.
                    # Grab each pane so tick labels discover their real widths.
                    for pane in workspace.visible_panes():
                        pane.grab()
                    QtTest.QTest.qWait(15)
                    app.processEvents()
                    geometry = tuple(round(viewport_time_x(pane, value), 5)
                        for pane in workspace.visible_panes()
                        for value in pane.getViewBox().viewRange()[0])
                    stable = stable+1 if geometry == previous else 0
                    previous = geometry
                    if stable >= 3:
                        return attempt+1
                raise AssertionError('Painted axis widths and queued canvas alignment did not settle')

            workspace.active = workspace.panes[0]
            workspace.set_time_lock(False)
            workspace.active.setXRange(.5, 1.5, padding=0)
            workspace.set_time_lock(True)
            paint_passes = {'time_lock': settle_painted_axes()}
            adopted = assert_ranges([.5, 1.5])
            pixel_checks = {'time_lock': time_pixel_alignment(workspace.visible_panes(), columns)}
            workspace.visible_panes()[-1].setXRange(.25, 1.75, padding=0)
            paint_passes['pan'] = settle_painted_axes()
            assert_ranges([.25, 1.75])
            pixel_checks['pan'] = time_pixel_alignment(workspace.visible_panes(), columns)
            for mode in ('x', 'y', 'xy', 'pan'):
                workspace.navigation_actions[mode].trigger()
                assert workspace.navigation_mode == mode
                assert workspace.navigation_actions[mode].isChecked()
                for pane in workspace.visible_panes():
                    enabled = list(pane.getViewBox().state['mouseEnabled'])
                    assert enabled == [mode != 'y', mode != 'x'], 'Menu/header mode and gesture mode differ'
            workspace.navigate('x')
            workspace.navigate('in')
            paint_passes['zoom_in'] = settle_painted_axes()
            assert_ranges()
            pixel_checks['zoom_in'] = time_pixel_alignment(workspace.visible_panes(), columns)
            workspace.navigate('out')
            workspace.navigate('reset')
            paint_passes['reset'] = settle_painted_axes()
            assert_ranges()
            pixel_checks['reset'] = time_pixel_alignment(workspace.visible_panes(), columns)
            saved = workspace.state()
            workspace.restore(saved)
            paint_passes['restore'] = settle_painted_axes()
            bounds = assert_ranges()
            pixel_checks['restore'] = time_pixel_alignment(workspace.visible_panes(), columns)
            heights = [pane.getViewBox().sceneBoundingRect().height() for pane in workspace.visible_panes()]
            assert min(heights) >= 150, f'{layout} at {size} crushed drawing heights to {heights}'
            assert len(workspace.visible_panes()) == LAYOUTS[layout][0]*LAYOUTS[layout][1]
            return {'layout': layout, 'theme': theme, 'window_size': size,
                    'adopted_ranges': adopted, 'restored_ranges': bounds, 'drawing_heights': heights,
                    'paint_settle_passes': paint_passes, 'time_pixel_alignment': pixel_checks,
                    'scroll_maximum': workspace.scroll.verticalScrollBar().maximum()}
        for layout in LAYOUTS:
            for theme in ('Dark', 'Light'):
                for size in ((1024, 680), (1536, 960)):
                    recorder.check(f'LAYOUT-{layout}-{theme}-{size[0]}',
                        lambda layout=layout, theme=theme, size=size: layout_theme_geometry(layout, theme, size),
                        'layout_time_modes', requires=('SYNTHETIC-SOURCE-EDGE-CASES',))

        def domain_independence():
            workspace.set_layout('Horizontal split')
            pane, other = workspace.visible_panes()
            pane.bind([synthetic[3].id])
            frequency = store.add(transform(synthetic[3], 'FFT'))
            other.bind([frequency.id])
            workspace.active = pane
            workspace.set_time_lock(True)
            other.setXRange(.1, .4, padding=0)
            pane.setXRange(.5, 1.5, padding=0)
            events()
            np.testing.assert_allclose(other.getViewBox().viewRange()[0], [.1, .4], rtol=0, atol=1e-7)
            other.bind([synthetic[2].id])
            workspace.set_time_lock(False)
            pane.setXRange(.1, .6, padding=0)
            other.setXRange(1.1, 1.8, padding=0)
            events()
            assert not np.allclose(pane.getViewBox().viewRange()[0], other.getViewBox().viewRange()[0])
            return {'frequency_independent': True, 'unlocked_time_independent': True}
        recorder.check('NON-TEMPORAL-AND-UNLOCKED-INDEPENDENCE', domain_independence, 'time_lock',
                       requires=('SYNTHETIC-SOURCE-EDGE-CASES',))

        def numerical_units_and_guards():
            power = synthetic[3]
            integral = transform(power, 'Cumulative integration')
            assert np.isclose(integral.y[-1], 120000.), 'Minute-clock integration did not use seconds'
            derived = transform(power, 'Differentiation')
            np.testing.assert_allclose(derived.y, 0, rtol=0, atol=1e-8)
            for channel in synthetic[:3]:
                try:
                    strict_clock(channel)
                except ValueError as exc:
                    recorder.result['expected_safety_rejections'].append({'scenario': 'strict-clock', 'source': channel.name, 'message': str(exc)})
                else:
                    raise AssertionError('Irregular/duplicate/masked clock silently accepted')
            for operation in ('Butterworth low-pass', 'FFT', 'Welch PSD'):
                try:
                    transform(synthetic[0], operation, cutoff=.1)
                except ValueError as exc:
                    recorder.result['expected_safety_rejections'].append({'scenario': operation, 'message': str(exc)})
                else:
                    raise AssertionError('Changing a cutoff bypassed an irregular-clock rejection')
            try:
                formula(store, f'Ch("{synthetic[0].id}") + Ch("{power.id}")')
            except ValueError as exc:
                recorder.result['expected_safety_rejections'].append({'scenario': 'mixed-clock-formula', 'message': str(exc)})
            else:
                raise AssertionError('Mixed clocks combined without explicit resampling')
            return {'integral_watt_seconds': float(integral.y[-1]), 'derivative_max_abs': float(np.max(np.abs(derived.y)))}
        recorder.check('NUMERICAL-UNITS-AND-SAFETY-REJECTIONS', numerical_units_and_guards, 'processing',
                       requires=('SYNTHETIC-SOURCE-EDGE-CASES',))

        def processing_preflight_controls():
            def select(channel):
                window.portal.search.clear()
                window.portal.rebuild()
                iterator = QtWidgets.QTreeWidgetItemIterator(window.portal.tree)
                while iterator.value():
                    item = iterator.value()
                    item.setSelected(item.data(0, QtCore.Qt.ItemDataRole.UserRole) == channel.id)
                    iterator += 1
                window.update_processing_preflight(reset_default=True)
                events()
            window.operation.setCurrentText('Butterworth low-pass')
            select(synthetic[3])
            cutoff = window.parameter_fields['cutoff'].value()
            assert 0 < cutoff < .5, 'The default cutoff is outside the verified Nyquist range'
            assert window.apply_button.isEnabled()
            assert 'nyquist' in window.parameter_help.text().lower()
            result = transform(synthetic[3], 'Butterworth low-pass', cutoff=cutoff)
            assert len(result.x) == len(synthetic[3].x)
            select(synthetic[0])
            assert not window.apply_button.isEnabled(), 'Irregular-clock Apply remains enabled'
            assert 'resampl' in window.parameter_help.text().lower(), 'Missing actionable resampling explanation'
            window.operation.setCurrentText('Cumulative integration')
            select(synthetic[4])
            assert 'unknown physical' in window.parameter_help.text().lower()
            unknown = transform(synthetic[4], 'Cumulative integration')
            assert 'wh' not in unknown.unit.lower(), 'Unknown source units were presented as known energy'
            return {'regular_cutoff_hz': cutoff, 'irregular_apply_blocked': True,
                    'unknown_unit_explanation': window.parameter_help.text()}
        recorder.check('PROCESSING-PREFLIGHT-VALID-DEFAULT-AND-EXPLANATIONS', processing_preflight_controls,
                       'processing', requires=('SYNTHETIC-SOURCE-EDGE-CASES',))

        def synthetic_gestures():
            window.tabs.setCurrentIndex(0)
            window.resize(1536, 960)
            workspace.set_layout('Single')
            pane = workspace.active
            pane.bind([synthetic[3].id, synthetic[2].id])
            pane.set_cursor_mode('off')
            rows = []
            def ranges():
                return (np.asarray(pane.getViewBox().viewRange()[0]),
                        [np.asarray(view.viewRange()[1]) for view in pane.y_views()])
            for mode in ('x', 'y', 'xy'):
                for gesture in ('wheel', 'box'):
                    workspace.navigate('reset')
                    workspace.navigate(mode)
                    events()
                    before_x, before_y = ranges()
                    bounds = pane.getViewBox().sceneBoundingRect()
                    if gesture == 'wheel':
                        position = pane.mapFromScene(bounds.center())
                        event = QtGui.QWheelEvent(QtCore.QPointF(position), QtCore.QPointF(pane.viewport().mapToGlobal(position)),
                            QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.MouseButton.NoButton,
                            QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
                        app.sendEvent(pane.viewport(), event)
                    else:
                        start = pane.mapFromScene(bounds.topLeft()+QtCore.QPointF(bounds.width()*.25, bounds.height()*.25))
                        end = pane.mapFromScene(bounds.topLeft()+QtCore.QPointF(bounds.width()*.75, bounds.height()*.75))
                        QtTest.QTest.mouseMove(pane.viewport(), start)
                        # QTest's mouseMove ``delay`` advances its synthetic
                        # timestamps on some Qt platforms without waiting in
                        # real time. Keep normal scene rate limiting enabled
                        # and pace a real drag so its moves reach GraphicsScene.
                        QtTest.QTest.qWait(25)
                        QtTest.QTest.mousePress(pane.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=start)
                        QtTest.QTest.qWait(25)
                        QtTest.QTest.mouseMove(pane.viewport(), start+(end-start)/2)
                        QtTest.QTest.qWait(25)
                        QtTest.QTest.mouseMove(pane.viewport(), end)
                        QtTest.QTest.qWait(25)
                        QtTest.QTest.mouseRelease(pane.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=end)
                    events()
                    after_x, after_y = ranges()
                    if mode == 'y':
                        np.testing.assert_allclose(after_x, before_x, rtol=0, atol=1e-7)
                    else:
                        assert np.ptp(after_x) < np.ptp(before_x)*.95, f'{mode} {gesture}: X gesture did not zoom the selected axis'
                    for first, last in zip(before_y, after_y):
                        if mode == 'x':
                            np.testing.assert_allclose(last, first, rtol=0, atol=1e-7)
                        else:
                            assert np.ptp(last) < np.ptp(first)*.95, 'Y gesture did not zoom an independent axis'
                    rows.append({'mode': mode, 'gesture': gesture})
            QtTest.QTest.keyClick(pane, QtCore.Qt.Key.Key_Escape)
            events()
            assert workspace.navigation_mode == 'pan' and workspace.navigation_actions['pan'].isChecked()
            assert list(pane.getViewBox().state['mouseEnabled']) == [True, True]
            pane.set_cursor_mode('dual')
            return {'qt_synthetic_gestures': rows, 'escape_shared_mode': 'pan',
                    'physical_mouse_and_dpi_checks': 'Unrun; see manual checks'}
        recorder.check('QT-WHEEL-BOX-KEYBOARD-SHARED-MODES', synthetic_gestures, 'navigation',
                       requires=('SYNTHETIC-SOURCE-EDGE-CASES',))

        def exact_workspace():
            assert len(fixture_stores) == 4
            expected_source_ids = {channel_id for other in fixture_stores.values() for channel_id in other.channels}
            assert expected_source_ids <= set(store.channels), 'A source partition is missing before preservation check'
            window.resize(1536, 960)
            workspace.set_layout('Single')
            pane = workspace.active
            pane.bind([synthetic[0].id])
            pane.lock_cursor(0, synthetic[0].id)
            pane.cursor_locks[0]['index'] = 1
            pane.restore_ranges(pane.state())
            views = [view.state() for view in window.workspaces]
            path = save_workspace(output/'source-preserving-workspace.json', store, views, window.ui_state())
            restored, saved_views, _ = load_workspace(path)
            assert set(restored.channels) == set(store.channels)
            assert set(restored.datasets) == set(store.datasets)
            for channel_id, channel in store.channels.items():
                other = restored.channels[channel_id]
                np.testing.assert_array_equal(other.x, channel.x)
                np.testing.assert_array_equal(other.y, channel.y)
                if channel.raw_y is not None:
                    np.testing.assert_array_equal(other.raw_y, channel.raw_y)
                np.testing.assert_array_equal(other.masks, channel.masks)
                assert other.shift == channel.shift
                assert other.unit == channel.unit and other.coordinate_unit == channel.coordinate_unit
            for dataset_id, dataset in store.datasets.items():
                pd.testing.assert_frame_equal(restored.datasets[dataset_id].frame, dataset.frame,
                                             check_exact=True, check_dtype=True)
                assert restored.datasets[dataset_id].frame.attrs == dataset.frame.attrs
            assert saved_views == views
            size = path.stat().st_size+sum(child.stat().st_size for child in path.parent.glob(path.stem+'.*.npz'))
            # Large exact-preserving snapshots are diagnostic outputs only. Keep
            # bounded reports/screenshots in CI artifacts, not 200+ MB per run.
            companion = path.parent/json.loads(path.read_text(encoding='utf-8'))['arrays']
            path.unlink()
            companion.unlink()
            return {'channels': len(restored.channels), 'datasets': len(restored.datasets),
                    'exact_source_cells': True, 'snapshot_bytes': size, 'snapshot_removed_after_verification': True}
        recorder.check('EXACT-REAL-SOURCE-WORKSPACE-ROUNDTRIP', exact_workspace, 'persistence',
                       requires=('REAL-FIXTURE-INTEGRITY-IMPORT', 'PER-FILE-CHECKBOX-AND-CLOSE-DATASET'))

        def exports_agree():
            assert fixture_stores
            workspace.set_layout('Single')
            representatives = [next(iter(other.channels)) for other in fixture_stores.values()]
            pane = workspace.active
            # Compatible time channels from different runs may intentionally be
            # overlaid; no alignment or matching-condition inference is made.
            compatible = [channel_id for channel_id in representatives if store.channels[channel_id].coordinate_kind == 'time']
            pane.bind(compatible+[synthetic[3].id])
            pane.cursor_lines[0].setValue(1)
            pane.cursor_lines[1].setValue(1.5)
            events()
            state = workspace.state()
            data, summary = interval_tables(store, state)
            for suffix in ('csv', 'xlsx', 'pdf', 'png'):
                path = output/('active-interval.'+suffix)
                exported, exported_summary = export_report(path, store, state)
                assert path.is_file() and path.stat().st_size > 100
                pd.testing.assert_frame_equal(exported, data)
                pd.testing.assert_frame_equal(exported_summary, summary)
            csv = pd.read_csv(output/'active-interval.csv')
            workbook = pd.read_excel(output/'active-interval.xlsx', sheet_name=None)
            assert list(workbook) == ['Active interval', 'Cursor summary']
            assert len(csv) == len(data) == len(workbook['Active interval'])
            disk_summary = workbook['Cursor summary']
            for field in ('cursor_A_X', 'cursor_B_X', 'A', 'B', 'ΔY'):
                np.testing.assert_allclose(disk_summary[field], summary[field], equal_nan=True)
            assert set(disk_summary.channel_id) == set(summary.channel_id)
            from openpyxl import load_workbook
            book = load_workbook(output/'active-interval.xlsx')
            sheet = book['Cursor summary']
            headers = [cell.value for cell in sheet[1]]
            color_column = headers.index('match_percent')+1
            assert any(sheet.cell(row, color_column).fill.fill_type == 'solid' for row in range(2, sheet.max_row+1))
            return {'summary_channels': len(summary), 'source_rows': len(data),
                    'formats': ['csv', 'xlsx', 'pdf', 'png'], 'cursor_and_match_metadata_verified': True}
        recorder.check('REAL-INTERVAL-EXPORT-FORMATS-AND-AGREEMENT', exports_agree, 'exports',
                       requires=('REAL-FIXTURE-INTEGRITY-IMPORT', 'PER-FILE-CHECKBOX-AND-CLOSE-DATASET',
                                 'SYNTHETIC-SOURCE-EDGE-CASES'))

        def sources_unchanged():
            assert manifest
            for entry in manifest['files']:
                assert sha256_file(samples/entry['filename']) == entry['sha256'], 'Original source file changed'
            return {'originals_verified': len(manifest['files'])}
        recorder.check('SOURCE-FILES-UNCHANGED', sources_unchanged, 'real_recordings',
                       requires=('REAL-FIXTURE-INTEGRITY-IMPORT',))
        window.grab().save(str(output/'accepted-workspace.png'))
    except Exception:
        recorder.result['runner_errors'].append({'id': recorder.current, 'error': traceback.format_exc()})
        recorder.save()
    finally:
        if window is not None:
            window.close()
            events()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        sys.excepthook = old_hook
