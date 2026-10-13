"""Read completed simulation packages without executing models or source code."""
import os
import posixpath
import re
import tempfile
import shutil
import zipfile
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET

import pandas as pd

from app_data import DataReadError
from app_simulation import SimulationCsvAdapter


def local_name(node):
    return node.tag.rsplit('}', 1)[-1] if isinstance(node.tag, str) else ''


def read_xml(data):
    if len(data) > 5 * 1024 * 1024:
        raise DataReadError('A simulation configuration exceeds the supported 5 MiB limit.')
    if re.search(br'<!DOCTYPE|<!ENTITY', data, re.I):
        raise DataReadError('Simulation XML must not contain external entities or a DTD.')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise DataReadError(f'Cannot parse simulation configuration: {exc}') from exc


def classify_file(name):
    lower = name.lower()
    if lower.endswith('_simulated_values.csv'): return 'Simulation values'
    if lower.endswith('_log.csv'): return 'Software log'
    if lower.endswith('.simconfig.xml'): return 'Simulation configuration'
    if lower.endswith('.batch.xml'): return 'Batch configuration'
    if lower.endswith('.xlsx'): return 'VT table'
    if lower.endswith(('.rac', '.raclib', '.raciflib')): return 'Source/library'
    if lower.endswith('_tableset.mat'): return 'MAT TableSet (artifact only)'
    if lower.endswith('.fmu'): return 'FMU (artifact only)'
    if '_console_output_' in lower and lower.endswith('.txt'): return 'Run diagnostics'
    if lower.endswith('.png'): return 'Previous visualization (not a data source)'
    return 'Other artifact'


class SimulationPackageAdapter(SimulationCsvAdapter):
    """Use only definitions belonging to the selected package's run."""

    def __init__(self, path, **settings):
        self.package_path = os.path.abspath(path)
        self.package_metadata = {}
        self.unit_evidence = []
        self.files = []
        self._temporary = tempfile.TemporaryDirectory(prefix='simulation_reference_')
        try:
            with zipfile.ZipFile(path) as archive:
                members = [entry for entry in archive.infolist() if not entry.is_dir()]
                if len(members) > 10000 or sum(entry.file_size for entry in members) > 1024 ** 3:
                    raise DataReadError('Simulation ZIP exceeds supported size or file count.')
                names = [entry.filename for entry in members]
                if len(set(names)) != len(names):
                    raise DataReadError('Simulation ZIP has duplicate member names; remove duplicates first.')
                self.files = [{'file': entry.filename, 'category': classify_file(entry.filename),
                               'bytes': entry.file_size} for entry in members]
                csvs = [name for name in names if name.lower().endswith('_simulated_values.csv')]
                if len(csvs) != 1:
                    raise DataReadError('Select a package containing exactly one *_simulated_values.csv '
                                        f'(found {len(csvs)}). Split multiple runs into separate ZIPs.')
                self.csv_member = csvs[0]
                self._inspect_definitions(archive, names)
                csv_path = Path(self._temporary.name) / 'simulation.csv'
                with archive.open(self.csv_member) as source, csv_path.open('wb') as destination:
                    shutil.copyfileobj(source, destination)
            detected = self.package_metadata.get('detected_pressure_unit')
            requested = settings.get('pressure_unit', 'unknown')
            if detected and requested in (None, 'unknown'):
                settings['pressure_unit'] = detected
            elif detected and requested != detected:
                self.unit_evidence.append(f'Manual source override {requested} differs from documented {detected}.')
            if self.package_metadata.get('detected_time_unit'):
                settings['time_unit'] = self.package_metadata['detected_time_unit']
                settings['high_resolution_time_column'] = 'accumulated_deltaTS'
            super().__init__(str(csv_path), **settings)
            rated = self.package_metadata.get('scenario_definitions', {}).get('heater_component_heater_power')
            if rated is not None and 'heater_power' in self.curves:
                numeric = pd.to_numeric(pd.Series([rated]), errors='coerce').iloc[0]
                if pd.notna(numeric) and numeric > 0:
                    self.curves['heater_power'].attrs['heater_on_reference_watts'] = float(numeric)
            self.path = self.package_path
            for curve in self.curves.values():
                curve.attrs['source_package'] = self.package_path
            self._check_recording()
            scenario = self.package_metadata.get('scenario_id', 'not specified')
            self.package_summary = f'Package: {len(self.files)} files; scenario {scenario}.'
        except (zipfile.BadZipFile, OSError) as exc:
            self.close()
            raise DataReadError(f'Cannot read simulation ZIP: {exc}') from exc
        except Exception:
            self.close()
            raise

    def _inspect_definitions(self, archive, names):
        prefix = PurePosixPath(self.csv_member).name[:-len('_simulated_values.csv')]
        tasks = []
        for name in names:
            if name.lower().endswith('.batch.xml'):
                root = read_xml(archive.read(name))
                for node in root.iter():
                    if local_name(node) == 'executionTask':
                        values = {local_name(child): (child.text or '').strip() for child in node}
                        if values.get('resultFilePrefix') == prefix:
                            tasks.append(values)
        if len(tasks) > 1:
            raise DataReadError('Several batch tasks match this CSV; use a package for one task.')
        task = tasks[0] if tasks else {}
        scenario_id = task.get('scenarioId')
        config_base = task.get('configPath', '').replace('\\', '/').rsplit('/', 1)[-1]
        configs = [name for name in names if name.lower().endswith('.simconfig.xml')]
        scenarios = []
        roots = {name: read_xml(archive.read(name)) for name in configs}
        for name, root in roots.items():
            if config_base and PurePosixPath(name).name != config_base:
                continue
            found = [node for node in root.iter() if local_name(node) == 'scenario'
                     and (not scenario_id or node.attrib.get('id') == scenario_id)]
            scenarios.extend((name, root, node) for node in found)
        # Do not silently choose one of several scenarios or machine variants.
        if len(scenarios) == 1:
            scenario_path, scenario_root, scenario = scenarios[0]
            self.package_metadata['scenario_id'] = scenario.attrib.get('id')
            self.package_metadata['scenario_file'] = scenario_path
            definitions = {node.attrib['id']: node.attrib.get('value') for node in scenario.iter()
                           if local_name(node) == 'definition' and 'id' in node.attrib and 'value' in node.attrib}
            self.package_metadata['scenario_definitions'] = definitions
            linked = []
            for node in scenario_root.iter():
                if local_name(node) == 'include':
                    relative = node.attrib.get('href', '').replace('\\', '/')
                    member = posixpath.normpath(posixpath.join(posixpath.dirname(scenario_path), relative))
                    if member in roots:
                        linked.append((member, roots[member]))
            project_prefix = posixpath.dirname(posixpath.dirname(scenario_path)) + '/'
        else:
            linked, project_prefix = [], None
            self.unit_evidence.append('No unique active scenario: configuration units were not inferred.')
        fields = {}
        documented_units = set()
        for name, root in linked:
            for node in root.iter():
                if local_name(node) == 'fields' and 'headerName' in node.attrib:
                    fields[node.attrib['headerName']] = dict(node.attrib)
            self.package_metadata['exporter_configuration'] = name
            if fields.get('time', {}).get('recordEntry') == 'accumulated_deltaTMin':
                formula = any(node.attrib.get('variable') == 'accumulated_deltaTMin'
                              and re.sub(r'\s+', '', node.attrib.get('value', '')) == 'accumulated_deltaTS/60'
                              for node in root.iter())
                if formula:
                    self.package_metadata['detected_time_unit'] = 'min'
                    self.unit_evidence.append(f'{name}: time = accumulated_deltaTS/60 (minutes).')
            pressure_export = fields.get('water_pressure', {})
            get_pressure = next((node for node in root.iter() if local_name(node) == 'interfaceFunction'
                                 and node.attrib.get('name') == 'get_pressure'), None)
            returns_same = get_pressure is not None and any(node.attrib.get('value') == 'currentPressure'
                                                           for node in get_pressure.iter())
            if pressure_export.get('recordEntry') != 'currentPressure' or not returns_same:
                continue
            for library in names:
                if not library.lower().endswith('.raciflib') or (project_prefix and not library.startswith(project_prefix)):
                    continue
                text = archive.read(library).decode('utf-8', errors='replace')
                # Inspect the documentation belonging to get_pressure, not unrelated Pa comments.
                for match in re.finditer(r'/\*\*(?:(?!\*/).)*\*/\s*readonly\s+interfaceFunction\s+get_pressure\b',
                                         text, flags=re.S):
                    documented = re.search(r'@return\s+pressure\b[^\n]*\bin\s+(Pa|kPa|mbar|bar)\b', match.group())
                    if documented:
                        documented_units.add(documented.group(1))
                        line = text[:match.start()].count('\n') + 1
                        self.unit_evidence.append(f'{library}:{line}: get_pressure return unit {documented.group(1)}; '
                                                  f'{name}: CSV water_pressure and get_pressure both use currentPressure.')
        self.package_metadata['exported_fields'] = fields
        if len(documented_units) == 1:
            self.package_metadata['detected_pressure_unit'] = documented_units.pop()
        elif documented_units:
            self.unit_evidence.append('Conflicting documented pressure units: pressure kept unconfirmed.')
        diagnostics = []
        for name in names:
            if classify_file(name) == 'Run diagnostics':
                text = re.sub(r'\x1b\[[0-9;]*m', '', archive.read(name).decode('utf-8', errors='replace'))
                diagnostics.append({'file': name, 'text': text})
                match = re.search(r'Simulated time was\s+([\d,]+)ms', text)
                if match:
                    self.package_metadata['console_duration_min'] = int(match.group(1).replace(',', '')) / 60000
        self.package_metadata['diagnostics'] = diagnostics

    def _check_recording(self):
        notes = []
        console = self.package_metadata.get('console_duration_min')
        if console is not None:
            delta = self.duration_min - console
            self.package_metadata['console_csv_duration_delta_min'] = delta
            if abs(delta) > .02:
                notes.append('Consistency warning: CSV duration differs from console simulated duration.')
        definitions = self.package_metadata.get('scenario_definitions', {})
        if 'loadMass' in definitions and 'load_mass' in self.frame:
            configured = pd.to_numeric(pd.Series([definitions['loadMass']]), errors='coerce').iloc[0]
            measured = pd.to_numeric(self.frame['load_mass'], errors='coerce').dropna()
            if pd.notna(configured) and not measured.empty and not measured.eq(configured).all():
                notes.append('Consistency warning: recorded load differs from selected scenario loadMass.')
        self.package_metadata['consistency_notes'] = notes

    def analysis_info(self):
        result = super().analysis_info()
        result.update(reference_type='zip', csv_member=self.csv_member,
                      unit_evidence=self.unit_evidence, package_metadata=self.package_metadata)
        return result

    def file_report(self):
        return pd.DataFrame(self.files)

    def close(self):
        self._temporary.cleanup()
