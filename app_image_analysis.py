"""Image graph analysis for the bundled appliance simulator plot format."""

import copy
import hashlib
import io
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from PIL import Image, ImageOps

from app_data import normalize_program_stage_series


SIMULATION_LEGEND_SPECS = [
    {
        'key': 'temperature', 'label': 'Temperature', 'color': '#343A40', 'bench_color': '#087E8B',
        'target_rgb': (32, 32, 32), 'ymin': 0.0, 'ymax': 80.0,
        'axis_calibration': (52.0, 80.0, 570.0, 0.0),
        'unit': '°C', 'block': 'Temperature', 'kind': 'analog',
        'bench_aliases': ('current temperature', 'water temperature', 'temperature'),
    },
    {
        'key': 'pressure', 'label': 'Water Pressure', 'color': '#0077A8', 'bench_color': '#B3442A',
        'target_rgb': (32, 188, 255), 'ymin': -200.0, 'ymax': 1600.0,
        'axis_calibration': (49.0, 1600.0, 617.0, -200.0),
        'unit': 'mbar', 'block': 'Pressure', 'kind': 'analog',
        'bench_aliases': ('water pressure', 'pressure'),
    },
    {
        'key': 'pre_wash_valve_open', 'label': 'Pre-wash Valve', 'color': '#007F8B', 'bench_color': '#C2410C',
        'target_rgb': (101, 201, 217), 'plot_rgb': (8, 169, 194),
        'state_on_y_range_px': (70, 140),
        'ymin': 0.0, 'ymax': 1.0,
        'axis_calibration': (78.0, 1.0, 570.0, 0.0),
        'unit': 'state', 'block': 'Actuator State', 'kind': 'digital',
        'bench_aliases': ('inlet valve pre', 'pre wash valve', 'inlet valve'),
    },
    {
        'key': 'wash_valve_open', 'label': 'Main Wash Valve', 'color': '#009688', 'bench_color': '#7B2CBF',
        'target_rgb': (178, 255, 247), 'plot_rgb': (0, 255, 230),
        'state_on_y_range_px': (60, 100),
        'ymin': 0.0, 'ymax': 1.0,
        'axis_calibration': (78.0, 1.0, 570.0, 0.0),
        'unit': 'state', 'block': 'Actuator State', 'kind': 'digital',
        'bench_aliases': ('main wash valve', 'out valve', 'out vavle', 'wash valve'),
    },
    {
        'key': 'water', 'label': 'Water Volume', 'color': '#548B00', 'bench_color': '#8338EC',
        'target_rgb': (119, 255, 32), 'ymin': 0.0, 'ymax': 80.0,
        'axis_calibration': (52.0, 80.0, 570.0, 0.0),
        'unit': 'L', 'block': 'Water Volume', 'kind': 'analog',
        'bench_aliases': ('water volume', 'water volume dst', 'actual vol'),
    },
    {
        'key': 'stwf_number', 'label': 'Stage ID (1–3)', 'color': '#7B2CBF', 'bench_color': '#8C6D31',
        'target_rgb': (148, 51, 215), 'ymin': 0.0, 'ymax': 3000.0,
        'axis_calibration': (63.0, 3000.0, 570.0, 0.0),
        'source_unit': 'program code',
        'unit': 'stage', 'block': 'Program Stage', 'kind': 'stage',
        'bench_aliases': ('wash stage',),
    },
    {
        'key': 'drain_open', 'label': 'Drain Pump', 'color': '#647D16', 'bench_color': '#D13C68',
        'target_rgb': (224, 255, 171), 'state_on_y_range_px': (70, 140),
        'ymin': 0.0, 'ymax': 1.0,
        'axis_calibration': (78.0, 1.0, 570.0, 0.0),
        'unit': 'state', 'block': 'Actuator State', 'kind': 'digital',
        'bench_aliases': ('drain valve', 'drain pump'),
    },
    {
        'key': 'calculated_remain_time', 'label': 'Remaining Time', 'color': '#B84A00', 'bench_color': '#137C8B',
        'target_rgb': (245, 119, 41), 'ymin': 0.0, 'ymax': 200.0,
        # Read from the signal's own tick marks, not the full plot frame. The
        # frame includes headroom above 200 and below 0 for this axis.
        'axis_calibration': (120.0, 200.0, 569.0, 0.0),
        'unit': 'min', 'block': 'Remaining Time', 'kind': 'analog',
        'bench_aliases': ('wash left time', 'remaining time', 'remain time'),
    },
    {
        'key': 'drum_speed', 'label': 'Drum Speed', 'color': '#C62828', 'bench_color': '#1967A0',
        'target_rgb': (255, 0, 0), 'ymin': -200.0, 'ymax': 1600.0,
        'axis_calibration': (49.0, 1600.0, 617.0, -200.0),
        'unit': 'RPM', 'block': 'Drum Speed', 'kind': 'analog',
        'bench_aliases': ('drump speed', 'drum speed', 'rpm'),
    },
    {
        'key': 'heater_power', 'label': 'Heater Relay', 'color': '#9A6B00', 'bench_color': '#1B7F4B',
        'target_rgb': (255, 227, 32), 'ymin': 0.0, 'ymax': 3000.0,
        'axis_calibration': (63.0, 3000.0, 570.0, 0.0),
        'source_unit': 'W',
        'unit': 'state', 'block': 'Actuator State', 'kind': 'digital',
        'relay_threshold': 0.0,
        'bench_aliases': ('heat valve', 'heater relay'),
    },
]


class SimulationImageAnalyzer:
    """Detect the simulator plot bounds and convert its colored traces to time series.

    The supplied simulator export is a multi-axis chart, so each trace is
    calibrated against its own source-axis range before it reaches the
    comparison renderer. Plot-frame coordinates are found from the image's
    axis spines, with scale-normalized fallback coordinates for this template.
    """

    REFERENCE_DURATION_MIN = 185.95
    REFERENCE_ASPECT_RATIO = 2500.0 / 704.0

    def __init__(self, image_path, duration_min=None, calibration=None):
        self.image_path = os.path.abspath(os.fspath(image_path))
        self.calibration = copy.deepcopy({} if calibration is None else calibration)
        if not isinstance(self.calibration, dict):
            raise ValueError("Image calibration must be a dictionary.")
        unknown = set(self.calibration) - {
            'duration_min', 'reference_height', 'axis_calibration', 'plot_bounds',
            'time_verified', 'axis_verified',
        }
        if unknown:
            raise ValueError(f"Unknown image calibration options: {', '.join(sorted(unknown))}")
        self.duration_min = float(duration_min if duration_min is not None else
                                  self.calibration.get('duration_min', self.REFERENCE_DURATION_MIN))
        self._duration_is_explicit = duration_min is not None or 'duration_min' in self.calibration
        self.reference_height = float(self.calibration.get('reference_height', 704.0))
        if not np.isfinite(self.duration_min) or self.duration_min <= 0:
            raise ValueError("The simulation duration must be a positive number of minutes.")
        if not np.isfinite(self.reference_height) or self.reference_height <= 0:
            raise ValueError("The calibration reference height must be positive.")
        overrides = self.calibration.get('axis_calibration', {})
        if not isinstance(overrides, dict):
            raise ValueError("Axis calibration must map signal keys to four tick coordinates/values.")
        known_keys = {spec['key'] for spec in SIMULATION_LEGEND_SPECS}
        if set(overrides) - known_keys:
            raise ValueError("An axis calibration refers to an unknown simulator signal.")
        for key, points in overrides.items():
            try:
                points = np.asarray(points, dtype=float)
            except (TypeError, ValueError) as exc:
                raise ValueError("Each axis calibration needs four finite tick coordinates/values.") from exc
            if points.shape != (4,) or not np.isfinite(points).all():
                raise ValueError("Each axis calibration needs four finite tick coordinates/values.")
            if float(points[0]) == float(points[2]) or float(points[1]) == float(points[3]):
                raise ValueError("Axis calibration ticks must have distinct positions and values.")
            overrides[key] = tuple(map(float, points))
        if not isinstance(self.calibration.get('time_verified', False), bool):
            raise ValueError("Time calibration confirmation must be true or false.")
        axis_verified = self.calibration.get('axis_verified', False)
        if isinstance(axis_verified, dict):
            if set(axis_verified) - known_keys or not all(isinstance(value, bool) for value in axis_verified.values()):
                raise ValueError("Axis confirmations must map known signal keys to true or false.")
        elif not isinstance(axis_verified, bool):
            raise ValueError("Axis calibration confirmation must be true/false or a signal-key dictionary.")
        self._cached_curves = None
        self._source_signature = None
        self._load_image()

    def _file_signature(self):
        stat = os.stat(self.image_path)
        return stat.st_mtime_ns, stat.st_size

    def source_is_current(self):
        """Tell the UI whether cached analysis still describes the selected file."""
        try:
            return self._file_signature() == self._source_signature
        except OSError:
            return False

    def clear_cache(self):
        self._cached_curves = None
        self._cached_settings = None

    def _settings_signature(self):
        return json.dumps(self._json_safe({
            'calibration': self.calibration, 'duration_min': self.duration_min,
            'reference_height': self.reference_height, 'specs': SIMULATION_LEGEND_SPECS
        }), sort_keys=True)

    def _load_image(self):
        if not os.path.isfile(self.image_path):
            raise FileNotFoundError(f"Image not found at {self.image_path}")
        signature = self._file_signature()
        with open(self.image_path, 'rb') as source:
            payload = source.read()
        if signature != self._file_signature():
            raise ValueError("The simulation image changed while it was being read. Analyze it again.")
        with Image.open(io.BytesIO(payload)) as source:
            original_size = source.size
            orientation = source.getexif().get(274, 1)
            normalized = ImageOps.exif_transpose(source)
            if 'A' in normalized.getbands() or 'transparency' in normalized.info:
                rgba = normalized.convert('RGBA')
                normalized = Image.alpha_composite(Image.new('RGBA', rgba.size, 'white'), rgba)
            self.image = np.asarray(normalized.convert('RGB'), dtype=np.uint8).copy()
        self._source_signature = signature
        self.source_metadata = {
            'path': self.image_path, 'sha256': hashlib.sha256(payload).hexdigest(),
            'modified_utc': datetime.fromtimestamp(signature[0] / 1e9, timezone.utc).isoformat(),
            'file_size_bytes': signature[1], 'original_image_size_px': list(original_size),
            'orientation_applied': orientation not in (None, 1),
        }
        self.height, self.width, _ = self.image.shape
        self._bounds_method = 'template fallback'
        self.plot_bounds = self._detect_plot_bounds()
        self.x_left, self.x_right, self.y_top, self.y_bottom = self.plot_bounds
        self.plot_box = self.image[self.y_top:self.y_bottom + 1, self.x_left:self.x_right + 1]
        self.box_h, self.box_w, _ = self.plot_box.shape
        if self.box_h < 10 or self.box_w < 10:
            raise ValueError("The simulator plot frame could not be detected in this image.")
        self.trace_diagnostics = {}
        self.actuator_analysis = {}
        self._drain_fill_active = np.zeros(self.box_w, dtype=bool)
        self._drain_observed = np.zeros(self.box_w, dtype=bool)
        self._drain_off_pixels = np.zeros(self.box_w, dtype=bool)
        self._drain_broad_active = np.zeros(self.box_w, dtype=bool)
        self._drain_fill_method = 'not analyzed'
        self._cached_curves = None
        self._cached_settings = None

    def _axis_calibration(self, spec):
        return self.calibration.get('axis_calibration', {}).get(spec['key'], spec.get('axis_calibration'))

    def _calibration_flags(self, spec):
        x_verified = bool(self.calibration.get('time_verified', False))
        axes_verified = self.calibration.get('axis_verified', False)
        y_verified = bool(axes_verified.get(spec['key'], False)) if isinstance(axes_verified, dict) else bool(axes_verified)
        return {'x_calibration_verified': x_verified, 'y_calibration_verified': y_verified,
                'calibration_verified': x_verified and y_verified, 'values_estimated_from_pixels': True}

    def _pixel_row_for_value(self, value, spec):
        calibration = self._axis_calibration(spec)
        if calibration:
            first_px, first_value, second_px, second_value = map(float, calibration)
            row = first_px + (value - first_value) / (second_value - first_value) * (second_px - first_px)
            return row * self.height / self.reference_height
        fraction = (spec['ymax'] - value) / (spec['ymax'] - spec['ymin'])
        return self.y_top + fraction * (self.y_bottom - self.y_top)

    def _state_band(self, spec, value):
        row = self._pixel_row_for_value(value, spec) - self.y_top
        half_width = max(1.0, self.height / self.reference_height)
        start = max(0, int(np.floor(row - half_width)))
        stop = min(self.box_h, int(np.ceil(row + half_width)) + 1)
        return slice(start, max(start, stop))

    @property
    def pixel_resolution_min(self):
        return self.duration_min / max(1, self.box_w - 1)

    def _detect_plot_bounds(self):
        requested = self.calibration.get('plot_bounds')
        if requested is not None:
            try:
                requested = np.asarray(requested, dtype=float)
            except (TypeError, ValueError) as exc:
                raise ValueError("Plot bounds must be four finite image-pixel coordinates.") from exc
            if requested.shape != (4,) or not np.isfinite(requested).all():
                raise ValueError("Plot bounds must be left, right, top, bottom image pixels.")
            left, right, top, bottom = map(int, requested)
            if not (0 <= left < right < self.width and 0 <= top < bottom < self.height):
                raise ValueError("The requested plot bounds fall outside the simulation image.")
            self._bounds_method = 'explicit image-pixel calibration'
            return left, right, top, bottom
        ratio = self.width / self.height if self.height else 0.0
        if not ratio or abs(ratio / self.REFERENCE_ASPECT_RATIO - 1.0) > 0.03:
            raise ValueError(
                "Unsupported simulator image layout. Select the standard 2500:704 "
                "reference plot or an image resized without cropping."
            )

        scale_x = self.width / 2500.0
        scale_y = self.height / 704.0
        fallback = (
            int(522 * scale_x), int(2110 * scale_x),
            int(28 * scale_y), int(618 * scale_y)
        )

        gray = self.image.max(axis=2)
        dark = gray < 190
        y0, y1 = int(0.05 * self.height), int(0.90 * self.height)
        x_candidates = []
        for low, high in ((0.18, 0.32), (0.65, 0.92)):
            left, right = int(low * self.width), int(high * self.width)
            counts = dark[y0:y1, left:right].sum(axis=0)
            if counts.size and counts.max() >= 0.65 * (y1 - y0):
                best = np.flatnonzero(counts >= counts.max() - 2) + left
                x_candidates.append(int(round(float(np.median(best)))))
            else:
                x_candidates.append(None)

        left, right = x_candidates
        if left is None or right is None or right <= left:
            left, right = fallback[0], fallback[1]

        plot_width = right - left
        row_counts = dark[:, left:right + 1].sum(axis=1)
        top_start, top_end = 0, int(0.15 * self.height)
        bottom_start, bottom_end = int(0.75 * self.height), int(0.96 * self.height)
        top_counts = row_counts[top_start:top_end]
        bottom_counts = row_counts[bottom_start:bottom_end]
        if top_counts.size and top_counts.max() >= 0.70 * plot_width:
            top = int(np.flatnonzero(top_counts >= top_counts.max() - 2)[0] + top_start)
        else:
            top = fallback[2]
        if bottom_counts.size and bottom_counts.max() >= 0.70 * plot_width:
            bottom = int(np.flatnonzero(bottom_counts >= bottom_counts.max() - 2)[-1] + bottom_start)
        else:
            bottom = fallback[3]

        if not (0 <= left < right < self.width and 0 <= top < bottom < self.height):
            return fallback
        self._bounds_method = 'detected axis spines' if (left, right, top, bottom) != fallback else 'template fallback'
        return left, right, top, bottom

    def _value_at_pixel_row(self, rows, spec):
        image_rows = rows.astype(float) + self.y_top
        calibration = self._axis_calibration(spec)
        if calibration:
            top_px, top_value, bottom_px, bottom_value = calibration
            scale_y = self.height / self.reference_height
            top_px *= scale_y
            bottom_px *= scale_y
            fraction = (image_rows - top_px) / (bottom_px - top_px)
            return top_value + fraction * (bottom_value - top_value)
        fraction = (image_rows - self.y_top) / max(1.0, self.y_bottom - self.y_top)
        return spec['ymax'] - fraction * (spec['ymax'] - spec['ymin'])

    @staticmethod
    def _white_composited_color_mask(rgb, trace_rgb, min_alpha=0.12,
                                     max_alpha=1.15, residual_tolerance=22.0):
        """Match a trace rendered over white, including antialiased shades.

        The simulator legend uses translucent swatches, while some plot strokes
        are drawn with a darker base color. A radius around the legend color
        misses those darker pixels and then median/interpolation turns vertical
        valve transitions into long false ON runs. Matching the color ray from
        white to the plot's base color handles both opaque and blended pixels.
        """
        pixels = rgb.astype(np.float32)
        white = np.full(3, 255.0, dtype=np.float32)
        trace = np.asarray(trace_rgb, dtype=np.float32)
        direction = white - trace
        norm_squared = float(np.dot(direction, direction))
        if norm_squared <= 0:
            return np.zeros(rgb.shape[:2], dtype=bool)

        alpha = np.einsum('ijk,k->ij', white - pixels, direction) / norm_squared
        expected = white - alpha[:, :, None] * direction
        residual = np.linalg.norm(pixels - expected, axis=2)
        return (
            (alpha >= min_alpha) & (alpha <= max_alpha)
            & (residual <= residual_tolerance)
        )

    @staticmethod
    def _clean_digital_ink(values):
        """Join one-column raster gaps and discard isolated transition pixels."""
        values = np.asarray(values, dtype=bool).copy()
        if values.size >= 3:
            values[1:-1] |= values[:-2] & values[2:]
            isolated = values & ~np.r_[False, values[:-1]] & ~np.r_[values[1:], False]
            values[isolated] = False
        return values

    @staticmethod
    def _remove_short_runs(values, minimum_columns=3):
        """Remove isolated color specks while keeping real rasterized pulses."""
        values = np.asarray(values, dtype=bool).copy()
        indices = np.flatnonzero(values)
        if not indices.size:
            return values
        runs = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
        for run in runs:
            if run.size < minimum_columns:
                values[run] = False
        return values

    @staticmethod
    def _bridge_short_gaps(values, maximum_gap=2):
        """Join tiny raster gaps inside a broad, otherwise continuous fill."""
        values = np.asarray(values, dtype=bool).copy()
        off_indices = np.flatnonzero(~values)
        if not off_indices.size:
            return values
        gaps = np.split(off_indices, np.flatnonzero(np.diff(off_indices) > 1) + 1)
        for gap in gaps:
            left = int(gap[0]) - 1
            right = int(gap[-1]) + 1
            if gap.size <= maximum_gap and left >= 0 and right < values.size and values[left] and values[right]:
                values[gap] = True
        return values

    def _drain_fill_state(self):
        """Detect the drain signal from its pale-green filled area, not its legend.

        In this simulator export, drain-open is drawn as a broad filled region.
        Matching that region by RGB distance and requiring vertical coverage
        rejects thin grid lines and isolated antialiased pixels. Float math is
        used here so RGB squared distances cannot overflow integer arrays.
        """
        pixels = self.plot_box.astype(np.float32)
        fill_rgb = np.asarray((206.0, 255.0, 121.0), dtype=np.float32)
        distance = np.sqrt(np.sum((pixels - fill_rgb) ** 2, axis=2))
        fill_pixels = distance <= 28.0
        coverage = fill_pixels.sum(axis=0)
        min_coverage = max(12, int(round(self.box_h * 0.08)))
        # Preserve each pixel-resolved ON/OFF pulse. Morphological cleanup and
        # a three-column minimum erased the first one- and two-column pump
        # pulses in this reference image, and gap filling merged real OFF gaps.
        broad_active = coverage >= min_coverage
        spec = next(item for item in SIMULATION_LEGEND_SPECS if item['key'] == 'drain_open')
        # Always read narrow strokes too. Restrict matching to the drain color
        # ray: a broad radius around the pale legend swatch also matches the
        # antialiased water trace and falsely invents pump pulses.
        stroke_mask = self._white_composited_color_mask(
            self.plot_box, fill_rgb, min_alpha=0.30, residual_tolerance=8.0
        )
        on_pixels = stroke_mask[self._state_band(spec, 1), :].any(axis=0)
        off_pixels = stroke_mask[self._state_band(spec, 0), :].any(axis=0)
        active = broad_active | on_pixels
        self._drain_observed = active | off_pixels
        self._drain_off_pixels = off_pixels
        self._drain_broad_active = broad_active
        self._drain_fill_method = 'pale-green fill plus calibrated ON/OFF strokes'
        return active, coverage, fill_pixels

    def _column_runs_as_minutes(self, mask):
        indices = np.flatnonzero(np.asarray(mask, dtype=bool))
        if not indices.size:
            return []
        runs = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
        scale = self.pixel_resolution_min
        return [
            (float(run[0] * scale), float(min(self.box_w - 1, run[-1] + 1) * scale))
            for run in runs
        ]

    def _analyze_actuator_overlap(self, curves):
        """Compare visible inlet pixels to drain-fill periods and mark occlusion."""
        drain_df = curves.get('drain_open', pd.DataFrame())
        if not isinstance(drain_df, pd.DataFrame) or drain_df.empty:
            self.actuator_analysis = {'available': False}
            return

        drain_active = pd.to_numeric(drain_df['value'], errors='coerce').fillna(0).to_numpy(dtype=float) > 0.5
        self._drain_fill_active = drain_active
        inlet_keys = ('pre_wash_valve_open', 'wash_valve_open')
        visible_overlaps = {}
        hidden_columns = {}

        for key in inlet_keys:
            curve = curves.get(key, pd.DataFrame())
            if not isinstance(curve, pd.DataFrame) or curve.empty:
                continue
            values = pd.to_numeric(curve['value'], errors='coerce').to_numpy(dtype=float, copy=True)
            visible_on = np.isfinite(values) & (values > 0.5)
            overlap = drain_active & visible_on
            observed = curve.get('observed', pd.Series(False, index=curve.index)).to_numpy(dtype=bool)
            visible_off = observed & np.isfinite(values) & (values <= 0.5)
            occluded = drain_active & ~visible_on & ~visible_off
            visible_overlaps[key] = overlap
            hidden_columns[key] = int(occluded.sum())

            # The pale-green pump fill can cover an inlet trace completely.
            # Do not turn an unobservable pixel into a false OFF state.
            values[occluded] = np.nan
            curves[key] = curve.assign(value=values, observed=observed & ~occluded)
            self.trace_diagnostics.setdefault(key, {})['visible_drain_overlap_columns'] = int(overlap.sum())
            self.trace_diagnostics.setdefault(key, {})['unknown_under_drain_fill_columns'] = int(occluded.sum())

        any_overlap = any(mask.any() for mask in visible_overlaps.values())
        drain_times = pd.to_numeric(drain_df['time_min'], errors='coerce').to_numpy(dtype=float)
        drain_on_indices = np.flatnonzero(drain_active)
        drain_off_indices = np.flatnonzero(drain_active[:-1] & ~drain_active[1:]) + 1
        drain_off_times = drain_times[drain_off_indices]

        drain_runs_indices = (
            np.split(drain_on_indices, np.flatnonzero(np.diff(drain_on_indices) > 1) + 1)
            if drain_on_indices.size else []
        )
        # A few narrow ON pulses precede the first broad filled pump interval.
        # Keep them as individual state runs, but group neighboring runs only
        # when measuring the complete first pump/pressure response.
        first_broad_run_index = next(
            (index for index, run in enumerate(drain_runs_indices)
             if self._drain_broad_active[run].any()),
            None
        )

        first_drain_pressure_response = None
        if drain_on_indices.size:
            first_drain_on = float(drain_times[drain_on_indices[0]])
            first_broad_fill_on = None
            if first_broad_run_index is not None:
                first_broad_run = drain_runs_indices[first_broad_run_index]
                first_broad_column = first_broad_run[self._drain_broad_active[first_broad_run]][0]
                first_broad_fill_on = float(drain_times[first_broad_column])
                episode_last_index = int(first_broad_run[-1])
                for next_run in drain_runs_indices[first_broad_run_index + 1:]:
                    gap_columns = int(next_run[0]) - episode_last_index - 1
                    if gap_columns > 2:
                        break
                    episode_last_index = int(next_run[-1])
                off_index = episode_last_index + 1
                first_drain_off = (
                    float(drain_times[off_index]) if off_index < len(drain_times)
                    else float(drain_times[-1])
                )
            else:
                later_off = drain_off_times[drain_off_times > first_drain_on]
                first_drain_off = float(later_off[0]) if later_off.size else float(drain_times[-1])
            pressure_curve = curves.get('pressure', pd.DataFrame())
            if isinstance(pressure_curve, pd.DataFrame) and not pressure_curve.empty:
                pressure_times = pd.to_numeric(
                    pressure_curve['time_min'], errors='coerce'
                ).to_numpy(dtype=float)
                pressure_values = pd.to_numeric(
                    pressure_curve['value'], errors='coerce'
                ).to_numpy(dtype=float)
                valid_pressure = np.isfinite(pressure_times) & np.isfinite(pressure_values)
                baseline_mask = (
                    valid_pressure
                    & (pressure_times >= max(0.0, first_drain_on - 1.5))
                    & (pressure_times < first_drain_on)
                )
                during_mask = (
                    valid_pressure
                    & (pressure_times >= first_drain_on)
                    & (pressure_times <= first_drain_off)
                )
                if baseline_mask.any() and during_mask.any():
                    # The pressure decline can begin before the broad drain
                    # fill is visibly rasterized. Look for a sustained drop
                    # in the ten minutes leading up to the fill edge and keep
                    # that inferred pressure event distinct from pump pixels.
                    decline_start = None
                    decline_baseline = None
                    candidate_indices = np.flatnonzero(
                        valid_pressure
                        & (pressure_times >= max(0.0, first_drain_on - 10.0))
                        & (pressure_times <= first_drain_on)
                    )
                    for candidate_index in candidate_indices:
                        candidate_time = float(pressure_times[candidate_index])
                        before_mask = (
                            valid_pressure
                            & (pressure_times >= max(0.0, candidate_time - 2.0))
                            & (pressure_times < candidate_time)
                        )
                        after_mask = (
                            valid_pressure
                            & (pressure_times >= candidate_time)
                            & (pressure_times <= candidate_time + 1.0)
                        )
                        if before_mask.sum() < 2 or after_mask.sum() < 2:
                            continue
                        before_level = float(np.median(pressure_values[before_mask]))
                        after_level = float(np.median(pressure_values[after_mask]))
                        meaningful_drop = max(20.0, abs(before_level) * 0.05)
                        if before_level - after_level >= meaningful_drop:
                            decline_start = candidate_time
                            decline_baseline = before_level
                            break

                    baseline = (
                        decline_baseline if decline_baseline is not None
                        else float(np.median(pressure_values[baseline_mask]))
                    )
                    active_values = pressure_values[during_mask]
                    minimum_index = int(np.flatnonzero(during_mask)[np.argmin(active_values)])
                    minimum = float(pressure_values[minimum_index])
                    drop = baseline - minimum
                    first_drain_pressure_response = {
                        'drain_on_min': first_drain_on,
                        'broad_fill_on_min': first_broad_fill_on,
                        'drain_off_min': first_drain_off,
                        'pressure_decline_start_min': decline_start,
                        'pressure_before_mbar': baseline,
                        'pressure_min_mbar': minimum,
                        'pressure_min_time_min': float(pressure_times[minimum_index]),
                        'pressure_drop_mbar': float(drop),
                        'pressure_drop_percent': float(drop / baseline * 100.0)
                        if abs(baseline) > 1e-9 else None,
                    }
            if first_drain_pressure_response is None:
                first_drain_pressure_response = {
                    'drain_on_min': first_drain_on,
                    'broad_fill_on_min': first_broad_fill_on,
                    'drain_off_min': first_drain_off,
                    'pressure_decline_start_min': None,
                    'pressure_before_mbar': None,
                    'pressure_min_mbar': None,
                    'pressure_min_time_min': None,
                    'pressure_drop_mbar': None,
                    'pressure_drop_percent': None,
                }

        main_curve = curves.get('wash_valve_open', pd.DataFrame())
        main_wash_on_times = np.array([], dtype=float)
        if isinstance(main_curve, pd.DataFrame) and not main_curve.empty:
            main_times = pd.to_numeric(main_curve['time_min'], errors='coerce').to_numpy(dtype=float)
            main_values = pd.to_numeric(main_curve['value'], errors='coerce').to_numpy(dtype=float)
            main_on = np.isfinite(main_values) & (main_values > 0.5)
            main_on_indices = np.flatnonzero(main_on & ~np.r_[False, main_on[:-1]])
            main_wash_on_times = main_times[main_on_indices]

        stage2_start = np.nan
        stage_curve = curves.get('stwf_number', pd.DataFrame())
        if isinstance(stage_curve, pd.DataFrame) and not stage_curve.empty:
            stage_times = pd.to_numeric(stage_curve['time_min'], errors='coerce').to_numpy(dtype=float)
            stage_values = pd.to_numeric(stage_curve['value'], errors='coerce').to_numpy(dtype=float)
            stage2 = np.isfinite(stage_values) & (stage_values == 2.0)
            stage2_indices = np.flatnonzero(stage2 & ~np.r_[False, stage2[:-1]])
            if stage2_indices.size:
                stage2_start = float(stage_times[stage2_indices[0]])

        first_rinse_handoff = None
        pixel_step = self.pixel_resolution_min
        if np.isfinite(stage2_start):
            handoffs = [
                (float(pump_off), float(valve_on))
                for pump_off in drain_off_times
                for valve_on in main_wash_on_times
                if abs(float(pump_off) - float(valve_on)) <= max(1.5 * pixel_step, 0.2)
                and abs(float(pump_off) - stage2_start) <= 1.0
            ]
            if handoffs:
                pump_off, valve_on = min(
                    handoffs,
                    key=lambda pair: abs(pair[0] - stage2_start) + abs(pair[1] - stage2_start)
                )
                first_rinse_handoff = {
                    'drain_off_min': pump_off,
                    'main_wash_on_min': valve_on,
                    'rinse_start_min': stage2_start,
                    'gap_min': valve_on - pump_off,
                    'pixel_resolution_min': pixel_step,
                }

        self.actuator_analysis = {
            'available': bool(self._drain_observed.any()),
            'drain_runs': self._column_runs_as_minutes(drain_active),
            'visible_overlap_runs': {
                key: self._column_runs_as_minutes(mask)
                for key, mask in visible_overlaps.items() if mask.any()
            },
            'visible_overlap': any_overlap,
            'unknown_columns': hidden_columns,
            'first_drain_pressure_response': first_drain_pressure_response,
            'first_rinse_handoff': first_rinse_handoff,
            'timing_uncertainty_min': pixel_step,
            'overlap_interpretation': 'Shared raster columns, not proof of simultaneous physical activation.',
        }

    @staticmethod
    def _dense_trace(found_x, found_values, width, kind, maximum_gap=2):
        """Fill only tiny raster gaps; leave occlusion and image edges unknown."""
        dense = np.full(width, np.nan, dtype=float)
        dense[found_x] = found_values
        for index, (left, right) in enumerate(zip(found_x[:-1], found_x[1:])):
            if not 1 < right - left <= maximum_gap + 1:
                continue
            first, second = float(found_values[index]), float(found_values[index + 1])
            if not np.isfinite(first) or not np.isfinite(second):
                continue
            if kind in ('heater', 'digital') and ((first > 0) != (second > 0)):
                continue
            if kind == 'stage' and not np.isclose(first, second, atol=1.0):
                continue
            dense[left:right + 1] = np.linspace(first, second, int(right - left + 1))
        return dense

    def _curve_frame(self, spec, values, observed=None, interpolated=None,
                     inferred=None, source_values=None):
        """Keep each pixel column, including gaps and its evidence classification."""
        values = np.asarray(values, dtype=float)
        count = len(values)
        false = np.zeros(count, dtype=bool)
        frame = pd.DataFrame({
            'time_min': np.arange(count, dtype=float) * self.pixel_resolution_min,
            'value': values,
            'observed': false.copy() if observed is None else np.asarray(observed, dtype=bool),
            'interpolated': false.copy() if interpolated is None else np.asarray(interpolated, dtype=bool),
            'inferred': false.copy() if inferred is None else np.asarray(inferred, dtype=bool),
            'source_value': values.copy() if source_values is None else np.asarray(source_values, dtype=float),
        })
        frame['source_min'] = frame['source_value']
        frame['source_max'] = frame['source_value']
        frame.attrs['analysis_metadata'] = {
            'source_path': self.image_path, 'source_sha256': self.source_metadata['sha256'],
            'profile': 'bundled simulator multi-axis export', 'signal_key': spec['key'],
            'duration_min': self.duration_min, 'pixel_resolution_min': self.pixel_resolution_min,
            'display_unit': spec['unit'], 'source_unit': spec.get('source_unit', spec['unit']),
            'axis_calibration': list(self._axis_calibration(spec) or []),
            'calibration_reference_height_px': self.reference_height,
        }
        flags = self._calibration_flags(spec)
        frame.attrs.update(flags)
        frame.attrs['analysis_metadata'].update(flags)
        return frame

    @staticmethod
    def _copy_curves(curves):
        result = {}
        for key, curve in curves.items():
            result[key] = curve.copy(deep=True)
            result[key].attrs = copy.deepcopy(curve.attrs)
        return result

    def extract_curves(self):
        """Return independent snapshots; modified source files invalidate cached pixels."""
        if not self.source_is_current():
            self._load_image()
        settings = self._settings_signature()
        if self._cached_curves is not None and settings == self._cached_settings:
            return self._copy_curves(self._cached_curves)
        if self._cached_settings is not None and settings != self._cached_settings:
            self._load_image()
        curves = {}
        rgb = self.plot_box.astype(np.int32)
        y_pixels = np.arange(self.box_h, dtype=float)[:, None]
        self.trace_diagnostics = {}

        for spec in SIMULATION_LEGEND_SPECS:
            target = np.asarray(spec['target_rgb'], dtype=np.int32)
            if spec['key'] == 'drain_open':
                active, coverage, fill_pixels = self._drain_fill_state()
                self._drain_fill_active = active
                self.trace_diagnostics[spec['key']] = {
                    'detected_columns': int(self._drain_observed.sum()),
                    'plot_columns': int(self.box_w),
                    'coverage_percent': round(100.0 * self._drain_observed.sum() / max(1, self.box_w), 1),
                    'on_columns': int(active.sum()),
                    'transition_columns': int((active & self._drain_off_pixels).sum()),
                    'fill_pixels': int(fill_pixels.sum()),
                    'fill_readout': self._drain_fill_method,
                    'pulse_intervals': self._column_runs_as_minutes(active),
                    'state_readout': 'Visible ON/OFF; absent fill interpreted as OFF for this export profile.',
                }
                # Absence of fill has profile-specific meaning, rather than
                # being direct OFF pixel evidence. Keep that distinction in
                # exports. An image with no drain evidence is not an all-OFF
                # reference; it is an undetected trace.
                observed = self._drain_observed
                if observed.any():
                    curves[spec['key']] = self._curve_frame(
                        spec, active.astype(float), observed=observed, inferred=~observed,
                        source_values=np.where(observed, active.astype(float), np.nan)
                    )
                    curves[spec['key']]['source_min'] = np.where(
                        self._drain_off_pixels, 0.0, curves[spec['key']]['source_min']
                    )
                else:
                    curves[spec['key']] = self._curve_frame(spec, np.array([], dtype=float))
                continue
            elif spec.get('plot_rgb'):
                mask = self._white_composited_color_mask(
                    rgb, spec['plot_rgb'], min_alpha=0.18, residual_tolerance=8.0
                )
            elif spec['key'] == 'heater_power':
                mask = (
                    (rgb[:, :, 0] > 200)
                    & (rgb[:, :, 1] > 200)
                    & (rgb[:, :, 2] < 80)
                )
            elif spec['key'] == 'calculated_remain_time':
                # The reference uses a saturated orange line. A broad RGB
                # radius around the old pale-orange sample picked up red
                # speed pixels and created the false sawtooth remaining-time
                # trace seen in comparison plots.
                red, green, blue = (rgb[:, :, channel] for channel in range(3))
                mask = (
                    (red > 200) & ((red - green) > 30)
                    & ((green - blue) > 15) & (green < 220)
                )
            elif spec['key'] == 'drum_speed':
                # Include the antialiased shades of the red RPM trace while
                # excluding the orange remaining-time line.
                red, green, blue = (rgb[:, :, channel] for channel in range(3))
                mask = (
                    (red > 200) & ((red - green) > 60)
                    & ((red - blue) > 60) & (np.abs(green - blue) < 25)
                )
            else:
                delta = rgb - target
                tolerance = int(spec.get('color_tolerance', 40))
                mask = np.sum(delta * delta, axis=2) <= tolerance * tolerance

            # Keep the actual data line, excluding plot borders and the dark
            # outside-axis labels that share the temperature trace color.
            mask[:2, :] = False
            mask[-2:, :] = False
            mask[:, :2] = False
            mask[:, -2:] = False
            if spec['key'] == 'temperature':
                # Use source tick limits, not a fractional crop that loses
                # legitimate higher temperatures in the head of the plot.
                ends = sorted((self._pixel_row_for_value(spec['ymin'], spec),
                               self._pixel_row_for_value(spec['ymax'], spec)))
                low = max(0, int(np.floor(ends[0] - self.y_top)) - 1)
                high = min(self.box_h, int(np.ceil(ends[1] - self.y_top)) + 2)
                mask[:low, :] = False
                mask[high:, :] = False

            found_x = np.flatnonzero(mask.any(axis=0))
            self.trace_diagnostics[spec['key']] = {
                'detected_columns': int(found_x.size),
                'plot_columns': int(self.box_w),
                'coverage_percent': round(100.0 * found_x.size / max(1, self.box_w), 1),
            }
            if not found_x.size:
                curves[spec['key']] = self._curve_frame(spec, np.array([], dtype=float))
                continue

            if spec['key'] in ('pre_wash_valve_open', 'wash_valve_open'):
                # A vertical transition can show both endpoints in the same
                # image column. Preserve ON evidence and record that timing
                # ambiguity. Do not erase single-column pulses or turn a
                # covered/missing trace into OFF.
                on_pixels = mask[self._state_band(spec, 1), :].any(axis=0)
                off_pixels = mask[self._state_band(spec, 0), :].any(axis=0)
                observed = on_pixels | off_pixels
                dense_values = np.full(self.box_w, np.nan, dtype=float)
                dense_values[off_pixels] = 0.0
                dense_values[on_pixels] = 1.0
                self.trace_diagnostics[spec['key']]['on_columns'] = int(on_pixels.sum())
                self.trace_diagnostics[spec['key']]['transition_columns'] = int((on_pixels & off_pixels).sum())
                self.trace_diagnostics[spec['key']]['state_readout'] = 'Calibrated ON/OFF pixels; unseen columns stay unknown.'
                curves[spec['key']] = self._curve_frame(spec, dense_values, observed=observed)
                curves[spec['key']]['source_min'] = np.where(off_pixels, 0.0, dense_values)
                curves[spec['key']]['source_max'] = np.where(on_pixels, 1.0, dense_values)
                continue

            # Median suppresses false top-pixel picks at vertical state changes.
            # The RPM signal is a dense pulse train: use the upper edge of each
            # pulse so the low-speed envelope and final spin ramps survive
            # rasterization into one value per image column.
            row_candidates = np.where(mask[:, found_x], y_pixels, np.nan)
            if spec['key'] == 'drum_speed':
                found_rows = np.nanmin(row_candidates, axis=0).astype(float)
            else:
                found_rows = np.nanmedian(row_candidates, axis=0).astype(float)
            found_values = self._value_at_pixel_row(found_rows, spec)
            edge_first = self._value_at_pixel_row(np.nanmin(row_candidates, axis=0), spec)
            edge_second = self._value_at_pixel_row(np.nanmax(row_candidates, axis=0), spec)
            if spec['key'] == 'drum_speed':
                found_values = np.maximum(edge_first, edge_second)
            observed = np.zeros(self.box_w, dtype=bool)
            observed[found_x] = True
            # Keep visible speed peaks and remaining-time resets. Smoothing
            # and deleting isolated high pixels concealed actual source ink.
            gap_limit = max(1, int(round(2.0 * (self.box_w - 1) / 1588.0)))
            if 'relay_threshold' in spec:
                # Rasterization cannot resolve power smaller than half a
                # source-axis pixel. Snap only that zero-line quantization
                # error; every distinguishable positive value means ON.
                zero_row = self._pixel_row_for_value(0.0, spec) - self.y_top
                power_per_pixel = abs(float(self._value_at_pixel_row(
                    np.asarray([zero_row + 1.0]), spec)[0]))
                found_values[np.abs(found_values) <= power_per_pixel * 0.5 + 1e-9] = 0.0
                source_values = self._dense_trace(found_x, found_values, self.box_w, 'heater', gap_limit)
                dense_values = np.where(np.isfinite(source_values),
                                        (source_values > spec['relay_threshold']).astype(float), np.nan)
                self.trace_diagnostics[spec['key']]['zero_resolution_w'] = power_per_pixel * 0.5
            else:
                source_values = self._dense_trace(found_x, found_values, self.box_w, spec['kind'], gap_limit)
                dense_values = source_values.copy()
                if spec['kind'] == 'stage':
                    dense_values = normalize_program_stage_series(dense_values).to_numpy(dtype=float)
            interpolated = np.isfinite(source_values) & ~observed
            curves[spec['key']] = self._curve_frame(
                spec, dense_values, observed=observed, interpolated=interpolated,
                source_values=source_values
            )
            # One image column can contain an entire pulse or vertical reset.
            # Export its visible extent too rather than claiming the chosen
            # representative value contains every event in that column.
            for column, bounds in (('source_min', np.minimum(edge_first, edge_second)),
                                   ('source_max', np.maximum(edge_first, edge_second))):
                column_values = np.full(self.box_w, np.nan, dtype=float)
                column_values[found_x] = bounds
                curves[spec['key']][column] = column_values
        self._analyze_actuator_overlap(curves)
        self._update_quality(curves)
        self._cached_curves = self._copy_curves(curves)
        self._cached_settings = settings
        return self._copy_curves(curves)

    @staticmethod
    def _json_safe(value):
        """Export nested diagnostics without NumPy objects or non-standard NaN JSON."""
        if isinstance(value, dict):
            return {str(key): SimulationImageAnalyzer._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, np.ndarray)):
            return [SimulationImageAnalyzer._json_safe(item) for item in value]
        if isinstance(value, np.generic):
            return SimulationImageAnalyzer._json_safe(value.item())
        if isinstance(value, float) and not np.isfinite(value):
            return None
        return value

    def _signal_notes(self, spec):
        notes = ['Tick calibration and time range use the bundled simulator export profile unless explicitly supplied.']
        if spec['key'] == 'drum_speed':
            notes.append('RPM is the visible upper pulse envelope per image column; individual subpixel pulses and covered peaks are unrecoverable.')
        elif spec['key'] == 'calculated_remain_time':
            notes.append('Estimate resets are preserved; only tiny missing raster gaps are interpolated.')
        elif spec['key'] == 'stwf_number':
            notes.append('Wash/Rinse/Spin is an inferred mapping of encoded source values: [500,1500), [1500,2500), and >=2500. Original program codes are retained in source_value.')
        elif spec['key'] == 'heater_power':
            notes.append('Source is heater power in W; positive resolved power means ON, zero/negative means OFF. Power within half a pixel of zero cannot be distinguished from zero.')
        elif spec['key'] == 'drain_open':
            notes.append('Visible pale-green fill or ON stroke means ON; absent fill is inferred OFF for this profile, not direct OFF evidence.')
        elif spec['key'] in ('pre_wash_valve_open', 'wash_valve_open'):
            notes.append('No physical inlet/drain interlock is assumed. Covered or missing state pixels remain unknown; transition columns have one-pixel timing ambiguity.')
        elif spec['key'] == 'pressure':
            notes.append('Source pressure axis is mbar; pulse duration in microseconds must not be compared without a supplied bench conversion.')
        return notes

    def _update_quality(self, curves):
        for spec in SIMULATION_LEGEND_SPECS:
            frame = curves[spec['key']]
            if frame.empty:
                finite = np.zeros(0, dtype=bool)
                observed = interpolated = inferred = finite
            else:
                finite = np.isfinite(frame['value'].to_numpy(dtype=float))
                observed = frame['observed'].to_numpy(dtype=bool) & finite
                interpolated = frame['interpolated'].to_numpy(dtype=bool) & finite
                inferred = frame['inferred'].to_numpy(dtype=bool) & finite
            denominator = max(1, self.box_w)
            known_count = int(finite.sum())
            fractions = {
                'observed_fraction': float(observed.sum() / denominator),
                'interpolated_fraction': float(interpolated.sum() / denominator),
                'inferred_fraction': float(inferred.sum() / denominator),
                'unknown_fraction': float((self.box_w - known_count) / denominator),
            }
            notes = self._signal_notes(spec)
            if known_count == 0:
                confidence = 'not detected'
            elif fractions['observed_fraction'] < 0.35:
                confidence = 'limited visible evidence'
            elif fractions['unknown_fraction'] > 0.15 or fractions['inferred_fraction'] > 0.15:
                confidence = 'partial / profile-derived'
            else:
                confidence = 'mostly visible'
            diag = self.trace_diagnostics.setdefault(spec['key'], {})
            diag.update(fractions)
            diag.update({
                'confidence': confidence,
                'confidence_meaning': 'Qualitative raster coverage, not statistical accuracy.',
                'known_columns': known_count, 'unknown_columns': self.box_w - known_count,
                'notes': notes,
            })
            diag.update(self._calibration_flags(spec))
            calibration = self._axis_calibration(spec)
            if calibration:
                first_px, first_value, second_px, second_value = map(float, calibration)
                diag['source_value_resolution_per_pixel'] = abs(
                    (second_value - first_value) / (second_px - first_px)
                    * self.reference_height / self.height
                )
            frame.attrs['analysis_metadata'].update({
                'confidence': confidence, 'quality': copy.deepcopy(fractions), 'notes': notes,
            })

    def analysis_info(self):
        """Return JSON-safe source, calibration, resolution and uncertainty metadata.

        This deliberately describes a known simulator profile. Detecting axis
        spines is not OCR or automatic unit identification for arbitrary plots.
        """
        self.extract_curves()
        return self._json_safe({
            'schema_version': 1,
            'source': copy.deepcopy(self.source_metadata),
            'image_size_px': [self.width, self.height],
            'plot_bounds_px': list(self.plot_bounds),
            'plot_size_px': [self.box_w, self.box_h],
            'bounds_method': self._bounds_method,
            'profile': 'bundled simulator multi-axis export (2500:704)',
            'profile_scope': 'Known trace colors and source tick positions; arbitrary charts require explicit calibration and matching trace definitions.',
            'duration_min': self.duration_min,
            'x_calibration_verified': bool(self.calibration.get('time_verified', False)),
            'calibration_verified': all(self._calibration_flags(spec)['calibration_verified']
                                        for spec in SIMULATION_LEGEND_SPECS),
            'values_estimated_from_pixels': True,
            'time_calibration': 'explicit' if self._duration_is_explicit or self.duration_min != self.REFERENCE_DURATION_MIN else 'reference profile',
            'pixel_resolution_min': self.pixel_resolution_min,
            'timing_uncertainty_min': self.pixel_resolution_min,
            'calibration_reference_height_px': self.reference_height,
            'calibration_overrides': copy.deepcopy(self.calibration),
            'traces': copy.deepcopy(self.trace_diagnostics),
            'actuator_analysis': copy.deepcopy(self.actuator_analysis),
            'limitations': [
                'Hidden trace pixels are not recovered from physical assumptions.',
                'Single image columns can contain several events; finer timing is unavailable.',
                'Shared colored pixels do not prove simultaneous physical actuator activity.',
                'Units, simulator time range and stage code semantics come from the profile or explicit calibration, not automatic OCR.',
            ],
        })

    def report_dataframe(self):
        """One exportable calibration/quality row per simulator legend signal."""
        self.extract_curves()
        rows = []
        for spec in SIMULATION_LEGEND_SPECS:
            diag = self.trace_diagnostics.get(spec['key'], {})
            rows.append({
                'signal_key': spec['key'], 'signal': spec['label'],
                'display_unit': spec['unit'], 'source_unit': spec.get('source_unit', spec['unit']),
                'source_path': self.image_path, 'source_sha256': self.source_metadata['sha256'],
                'image_width_px': self.width, 'image_height_px': self.height,
                'plot_width_px': self.box_w, 'plot_height_px': self.box_h,
                'bounds_method': self._bounds_method, 'duration_min': self.duration_min,
                **self._calibration_flags(spec),
                'time_pixel_resolution_min': self.pixel_resolution_min,
                'axis_calibration': json.dumps(self._json_safe(self._axis_calibration(spec))),
                'calibration_reference_height_px': self.reference_height,
                'source_value_resolution_per_pixel': diag.get('source_value_resolution_per_pixel'),
                'detected_columns': diag.get('detected_columns', 0),
                'known_columns': diag.get('known_columns', 0),
                'observed_fraction': diag.get('observed_fraction', 0.0),
                'interpolated_fraction': diag.get('interpolated_fraction', 0.0),
                'inferred_fraction': diag.get('inferred_fraction', 0.0),
                'unknown_fraction': diag.get('unknown_fraction', 1.0),
                'confidence': diag.get('confidence', 'not detected'),
                'confidence_meaning': 'Qualitative raster coverage, not statistical accuracy.',
                'notes': ' '.join(diag.get('notes', self._signal_notes(spec))),
            })
        return pd.DataFrame(rows)

    def render_preview(self, curves=None):
        """Render each extracted signal in its own independently scaled panel."""
        import matplotlib.pyplot as plt
        import math

        curves = curves if curves is not None else self.extract_curves()
        if not any(
            isinstance(curves.get(spec['key']), pd.DataFrame)
            and not curves[spec['key']].empty
            for spec in SIMULATION_LEGEND_SPECS
        ):
            raise ValueError("No colored simulator traces were detected in the image.")

        column_count = 2
        row_count = int(math.ceil(len(SIMULATION_LEGEND_SPECS) / column_count))
        fig, axes_raw = plt.subplots(
            row_count, column_count, figsize=(15.2, 9.2), dpi=90,
            sharex=True, squeeze=False
        )
        axes = list(axes_raw.flat)
        fig.suptitle('Simulation Image Analysis · One Scale per Signal',
                     fontsize=14, fontweight='bold', color='#17324D', y=0.992)
        drain_runs = self.actuator_analysis.get('drain_runs', [])
        first_drain_response = self.actuator_analysis.get('first_drain_pressure_response')
        first_rinse_handoff = self.actuator_analysis.get('first_rinse_handoff')
        for axis, spec in zip(axes, SIMULATION_LEGEND_SPECS):
            curve = curves.get(spec['key'], pd.DataFrame())
            axis.grid(True, linestyle=':', color='#D8DEE6', alpha=0.75)
            unit = '' if spec['unit'] in ('state', 'stage') else f" · {spec['unit']}"
            axis.set_title(f"{spec['label']}{unit}", loc='left', fontsize=9,
                           fontweight='bold', color='#344054', pad=3)
            if not isinstance(curve, pd.DataFrame) or curve.empty:
                axis.text(0.5, 0.5, 'Trace not detected', transform=axis.transAxes,
                          ha='center', va='center', color='#667085', fontsize=8)
                axis.set_ylim(0, 1)
                axis.set_xlabel('Elapsed time (min)', fontsize=7)
                axis.tick_params(axis='both', labelsize=7, colors='#475467')
                continue

            tx = pd.to_numeric(curve['time_min'], errors='coerce').to_numpy(dtype=float)
            values = pd.to_numeric(curve['value'], errors='coerce').to_numpy(dtype=float)
            valid_x = np.isfinite(tx)
            tx, values = tx[valid_x], values[valid_x]

            if spec['key'] in ('pre_wash_valve_open', 'wash_valve_open'):
                for start, end in drain_runs:
                    axis.axvspan(start, end, color='#647D16', alpha=0.12, linewidth=0, zorder=0)
                axis.text(0.99, 0.05, 'Shaded: drain fill; valve pixels may be hidden',
                          transform=axis.transAxes, ha='right', va='bottom',
                          fontsize=6.5, color='#59651B')

            if first_rinse_handoff and spec['key'] in ('drain_open', 'wash_valve_open'):
                handoff_time = first_rinse_handoff['main_wash_on_min']
                axis.axvline(handoff_time, color='#344054', linestyle=':', linewidth=0.9, zorder=3)
                if spec['key'] == 'wash_valve_open':
                    axis.text(
                        0.99, 0.88, f"First-rinse handoff ≈ {handoff_time:.1f} min",
                        transform=axis.transAxes, ha='right', va='top',
                        fontsize=7, color='#344054'
                    )

            if first_drain_response and spec['key'] in ('drain_open', 'pressure'):
                first_pulse_start = first_drain_response['drain_on_min']
                broad_fill_start = first_drain_response.get('broad_fill_on_min')
                axis.axvline(first_pulse_start, color='#475467', linestyle=':', linewidth=0.9, zorder=3)
                if broad_fill_start is not None and broad_fill_start != first_pulse_start:
                    axis.axvline(
                        broad_fill_start, color='#647D16', linestyle='-.',
                        linewidth=0.9, zorder=3
                    )
                pressure_decline_start = first_drain_response.get('pressure_decline_start_min')
                if pressure_decline_start is not None:
                    axis.axvline(
                        pressure_decline_start, color='#D97706', linestyle='--',
                        linewidth=0.9, alpha=0.9, zorder=3
                    )
                if spec['key'] == 'pressure' and first_drain_response.get('pressure_drop_mbar') is not None:
                    broad_fill_note = (
                        f"broad fill ≈ {broad_fill_start:.1f} min · "
                        if broad_fill_start is not None else ""
                    )
                    axis.text(
                        0.99, 0.95,
                        f"Pressure decline ≈ {pressure_decline_start:.1f} min · "
                        f"first pump pulse ≈ {first_pulse_start:.1f} min · "
                        f"{broad_fill_note}drop ≈ {first_drain_response['pressure_drop_mbar']:.0f} mbar"
                        if pressure_decline_start is not None else
                        f"First pump pulse ≈ {first_pulse_start:.1f} min · {broad_fill_note}pressure drops "
                        f"≈ {first_drain_response['pressure_drop_mbar']:.0f} mbar",
                        transform=axis.transAxes, ha='right', va='top',
                        fontsize=7, color='#344054'
                    )

            if spec['kind'] == 'digital':
                axis.step(tx, values, where='post', color=spec['color'], lw=1.25,
                          zorder=2, solid_capstyle='butt')
                axis.set_ylim(-0.04, 1.04)
                axis.set_yticks([0, 1])
                axis.set_yticklabels(['OFF', 'ON'], fontsize=7)
            elif spec['kind'] == 'stage':
                axis.step(tx, values, where='post', color=spec['color'], lw=1.3)
                axis.set_ylim(0.8, 3.2)
                axis.set_yticks([1, 2, 3])
                axis.set_yticklabels(['1 Wash', '2 Rinse', '3 Spin'], fontsize=7)
            else:
                if spec['key'] == 'drum_speed' and {'source_min', 'source_max'} <= set(curve.columns):
                    source_low = pd.to_numeric(curve['source_min'], errors='coerce').to_numpy(dtype=float)[valid_x]
                    source_high = pd.to_numeric(curve['source_max'], errors='coerce').to_numpy(dtype=float)[valid_x]
                    axis.fill_between(tx, source_low, source_high, color=spec['color'],
                                      alpha=0.18, linewidth=0, zorder=1)
                axis.plot(tx, values, color=spec['color'], lw=1.15)
                finite = values[np.isfinite(values)]
                if spec['key'] == 'drum_speed' and {'source_min', 'source_max'} <= set(curve.columns):
                    finite = np.r_[finite, source_low[np.isfinite(source_low)],
                                   source_high[np.isfinite(source_high)]]
                if finite.size:
                    low, high = float(finite.min()), float(finite.max())
                    pad = max((high - low) * 0.07, abs(high) * 0.02, 0.5)
                    axis.set_ylim(max(0.0, low - pad) if low >= 0 else low - pad, high + pad)
            finite_values = np.isfinite(values)
            if finite_values.any():
                isolated = finite_values & ~np.r_[False, finite_values[:-1]] & ~np.r_[finite_values[1:], False]
                if isolated.any():
                    axis.scatter(tx[isolated], values[isolated], s=9, color=spec['color'], zorder=4)
            y_label = '' if spec['unit'] in ('state', 'stage') else spec['unit']
            axis.set_ylabel(y_label, fontsize=7, fontweight='bold', color='#475467')
            axis.tick_params(axis='both', labelsize=7, colors='#475467')
            axis.set_xlabel('Elapsed time (min)', fontsize=7)
            axis.set_xlim(0, self.duration_min)

        for axis in axes[len(SIMULATION_LEGEND_SPECS):]:
            axis.set_visible(False)
        axes[0].set_xlim(0, self.duration_min)
        fig.text(0.055, 0.009, 'Gaps are unobservable pixels. Points preserve isolated samples; RPM shading shows the visible pulse range. Scales use the simulator profile.',
                 fontsize=7, color='#475467')
        fig.subplots_adjust(left=0.055, right=0.985, top=0.955, bottom=0.070,
                            wspace=0.16, hspace=0.38)
        return fig, axes

    def report_text(self):
        if not self.source_is_current():
            self.extract_curves()
        if not self.trace_diagnostics:
            return f"Plot frame detected: {self.box_w} × {self.box_h} px. Run analysis to inspect trace coverage."
        detected = sum(item['detected_columns'] > 0 for item in self.trace_diagnostics.values())
        coverage = ', '.join(
            f"{spec['label']}: {self.trace_diagnostics.get(spec['key'], {}).get('coverage_percent', 0):g}%"
            for spec in SIMULATION_LEGEND_SPECS
        )
        overlap = self.actuator_analysis
        handoff = overlap.get('first_rinse_handoff')
        if not overlap.get('available'):
            actuator_summary = "Inlet/drain overlap: unavailable; drain fill was not detected."
        elif overlap.get('visible_overlap'):
            overlap_windows = []
            for runs in overlap.get('visible_overlap_runs', {}).values():
                overlap_windows.extend(runs)
            overlap_windows.sort()
            window_text = ', '.join(
                f"{start:.1f}–{end:.1f} min" for start, end in overlap_windows[:4]
            )
            actuator_summary = "Visible inlet/drain ON pixels overlap"
            if window_text:
                actuator_summary += f" at {window_text}."
            else:
                actuator_summary += "."
            actuator_summary += " Shared image columns do not establish simultaneous physical activation."
        else:
            drain_windows = ', '.join(
                f"{start:.2f}–{end:.2f}" for start, end in overlap.get('drain_runs', [])
            )
            actuator_summary = (
                "No visible inlet/drain overlap. Pixel-detected drain ON intervals: "
                f"{drain_windows or 'none'} min. Inlet pixels covered by drain fill remain unknown unless an ON/OFF stroke is visible."
            )
        if handoff:
            actuator_summary += (
                f" First-rinse handoff: drain OFF and main-wash ON at "
                f"about {handoff['main_wash_on_min']:.1f} min; "
                f"rinse stage begins near {handoff['rinse_start_min']:.1f} min."
            )
        first_drain = overlap.get('first_drain_pressure_response')
        if first_drain and first_drain.get('pressure_drop_mbar') is not None:
            drop = first_drain['pressure_drop_mbar']
            before = first_drain['pressure_before_mbar']
            minimum = first_drain['pressure_min_mbar']
            if drop > 0:
                decline_start = first_drain.get('pressure_decline_start_min')
                onset_text = (
                    f"Pressure begins falling near {decline_start:.1f} min, before the "
                    "first detected drain pulse; "
                    if decline_start is not None and decline_start < first_drain['drain_on_min']
                    else ""
                )
                broad_fill = first_drain.get('broad_fill_on_min')
                broad_fill_text = (
                    f" The broad pump-fill region begins near {broad_fill:.2f} min."
                    if broad_fill is not None else ""
                )
                actuator_summary += (
                    f" First drain pulse appears near {first_drain['drain_on_min']:.2f} min."
                    f"{broad_fill_text} "
                    f"{onset_text}pressure falls from about {before:.0f} to {minimum:.0f} mbar "
                    f"(−{drop:.0f} mbar) during the pump interval."
                )
        return (
            f"Plot frame {self.box_w} × {self.box_h} px · "
            f"{detected}/{len(SIMULATION_LEGEND_SPECS)} traces detected. "
            f"Time resolution ≈ {self.pixel_resolution_min:.3f} min/pixel. "
            f"Source tick calibration uses the bundled simulator profile; stage names are inferred from program codes. "
            f"Visible color coverage: {coverage} · {actuator_summary} "
            "Unseen pixels remain gaps; short interpolations, profile-derived OFF states and per-signal uncertainty are listed in the analysis report."
        )


# Backward-compatible name used by older builds and plugins.
SimulationImageDigitizer = SimulationImageAnalyzer
