import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import re
import textwrap
from matplotlib.ticker import MaxNLocator
from matplotlib.backend_bases import PickEvent
from app_data import classify_signal_kind, normalize_control_series, normalize_program_stage_series
from app_layout import SignalFigureLayout, readable_text_color, set_signal_time_bounds
from app_symbols import attach_lock_state_icons

AXIS_SPINE_GAP_POINTS = 38


def format_axis_title(signals):
    """Return a compact title for a collection of related signals."""
    if not signals:
        return ""
    if len(signals) == 1:
        return str(signals[0]['name'])
    names = [str(signal['name']).lower() for signal in signals]
    if all(signal['is_digital'] for signal in signals):
        if all(any(key in name for key in ('door', 'lock')) for name in names):
            return "Door Lock State"
        return "Actuator State (0/1)"
    return " / ".join(str(signal['name']) for signal in signals[:2])


def compact_axis_label(name, max_line_length=17):
    """Keep axis labels readable without letting long names crowd neighbors."""
    label = re.sub(r'\s+', ' ', str(name)).strip()
    if len(label) <= max_line_length:
        return label

    unit_match = re.search(r'\s+(\([^()]+\))$', label)
    if unit_match:
        description = label[:unit_match.start()].strip()
        unit = unit_match.group(1)
        if len(description) > max_line_length:
            description = textwrap.shorten(
                description, width=max_line_length, placeholder='…'
            )
        return f"{description}\n{unit}"

    return '\n'.join(textwrap.wrap(
        label, width=max_line_length, max_lines=2, placeholder='…'
    ))


def axis_title_for_unit(unit_label):
    unit = str(unit_label).strip().lower()
    unit_names = {
        '°c': 'Temperature', 'c': 'Temperature', 'rpm': 'Speed',
        'mbar': 'Pressure', 'bar': 'Pressure', 'l': 'Volume',
        'kg': 'Weight', 'g': 'Weight', 'v': 'Voltage', 'a': 'Current',
        'w': 'Power', 'kw': 'Power', 'wh': 'Energy', 'kwh': 'Energy',
        'hz': 'Frequency'
    }
    descriptor = unit_names.get(unit)
    return f"{descriptor} ({unit_label})" if descriptor else str(unit_label)


def channel_name_without_unit(signal):
    return re.sub(r'\s+\([^()]+\)$', '', str(signal['name'])).strip()


def canonical_unit_key(unit_label):
    """Normalize common unit spellings so equivalent signals share one scale."""
    unit = re.sub(r'\s+', '', str(unit_label)).lower()
    aliases = {
        'ºc': '°c', 'c': '°c', 'degc': '°c', 'degreesc': '°c',
        'litre': 'l', 'litres': 'l', 'liter': 'l', 'liters': 'l',
        'grams': 'g', 'gram': 'g', 'kilograms': 'kg', 'kilogram': 'kg',
        'volts': 'v', 'volt': 'v', 'amps': 'a', 'amp': 'a', 'amperes': 'a',
        'watts': 'w', 'watt': 'w', 'kilowatts': 'kw', 'kilowatt': 'kw',
        'rpm.': 'rpm', 'mbar.': 'mbar'
    }
    return aliases.get(unit, unit)


def enable_draggable_legend(legend):
    """Enable reliable legend dragging across the main and twinned axes."""
    if legend is None:
        return
    canvas = legend.figure.canvas
    previous = getattr(legend, '_signal_drag_press_cid', None)
    if previous is not None:
        canvas.mpl_disconnect(previous)
    draggable = legend.set_draggable(True, use_blit=False)
    if draggable is None:
        return
    legend._signal_drag_disposed = False

    def pick_across_axes(event):
        if (event.button != 1 or not legend.get_visible() or draggable.got_artist
                or getattr(legend, '_signal_drag_disposed', False)):
            return
        if legend.contains(event)[0]:
            # A twin axis can be topmost under the legend. Picking explicitly
            # avoids the native artist filter ignoring the owning lower axis.
            draggable.on_pick(PickEvent('pick_event', canvas, event, legend))

    legend._signal_drag_press_cid = canvas.mpl_connect('button_press_event', pick_across_axes)


def disable_draggable_legend(legend):
    """Release the callbacks held by a legend before replacing its figure."""
    if legend is None:
        return
    legend._signal_drag_disposed = True
    press_cid = getattr(legend, '_signal_drag_press_cid', None)
    if press_cid is not None:
        legend.figure.canvas.mpl_disconnect(press_cid)
        legend._signal_drag_press_cid = None
    legend.set_draggable(False)


def _set_lock_state_ticks(axis, side, color):
    limits = axis.get_ylim()
    axis.set_yticks([0, 1])
    axis.set_yticklabels(['', ''])
    axis.tick_params(axis='y', labelrotation=0)
    attach_lock_state_icons(axis, side, color)
    # Fixed tick locations must not expand a user-selected Y range.
    axis.set_ylim(limits)


class DashboardPlotter:
    @staticmethod
    def render(aligned_df, grid_widgets, options):
        if aligned_df is None or aligned_df.empty or 'relative_minutes' not in aligned_df.columns:
            return None, [], [], [], [], "Load and align a dataset with valid elapsed-time values before plotting."

        def panel_number(conf):
            match = re.fullmatch(r"Panel\s+(\d+)", str(conf['panel'].get()).strip())
            if not match or not 1 <= int(match.group(1)) <= 10:
                return None
            return int(match.group(1))

        def limits_for_signal(signal):
            values = np.asarray(signal['y'], dtype=float)
            finite = values[np.isfinite(values)]
            if finite.size == 0:
                data_min, data_max = 0.0, 1.0
            else:
                data_min, data_max = float(np.min(finite)), float(np.max(finite))

            try:
                requested_min = float(signal['ymin']) if signal['ymin'] else None
                requested_max = float(signal['ymax']) if signal['ymax'] else None
            except (TypeError, ValueError) as exc:
                plt.close(fig)
                raise ValueError(f"Y-axis limits for '{signal['name']}' must be numeric.") from exc

            if requested_min is not None and not np.isfinite(requested_min):
                plt.close(fig)
                raise ValueError(f"Y-min for '{signal['name']}' must be finite.")
            if requested_max is not None and not np.isfinite(requested_max):
                plt.close(fig)
                raise ValueError(f"Y-max for '{signal['name']}' must be finite.")

            if signal['is_digital'] and requested_min is None and requested_max is None:
                return -0.04, 1.04
            if signal.get('is_stage') and requested_min is None and requested_max is None:
                return 0.8, 3.2

            span = data_max - data_min
            if span == 0:
                padding = max(abs(data_min) * 0.05, 1.0)
            else:
                padding = span * 0.08
            auto_min = data_min - padding
            auto_max = data_max + padding
            if data_min >= 0 and auto_min < 0:
                auto_min = 0.0

            low = requested_min if requested_min is not None else auto_min
            high = requested_max if requested_max is not None else auto_max
            if low >= high:
                plt.close(fig)
                raise ValueError(f"Y-min for '{signal['name']}' must be less than its Y-max.")
            return low, high

        enabled = [conf for signal_id, conf in grid_widgets.items()
                   if conf['enabled'].get() and conf.get('data_col', signal_id) in aligned_df.columns]
        if any(panel_number(conf) is None for conf in enabled):
            return None, [], [], [], [], "A selected signal has an invalid panel. Choose Panel 1 through Panel 10 or reload the preset."

        active_panels = sorted(
            {conf['panel'].get() for conf in enabled},
            key=lambda name: int(name.replace("Panel ", ""))
        )
        if not active_panels:
            return None, [], [], [], [], "Please enable at least one signal in the configuration grid."

        panel_map = {name: index for index, name in enumerate(active_panels)}
        n_panels = len(active_panels)
        fig_height = max(6.5, 1.65 * n_panels + 0.75)
        fig, axes_raw = plt.subplots(nrows=n_panels, ncols=1, figsize=(15, fig_height), sharex=True)
        if isinstance(axes_raw, np.ndarray):
            axes = list(axes_raw.flat)
        elif isinstance(axes_raw, list):
            axes = axes_raw
        else:
            axes = [axes_raw]

        font_size = max(8, min(16, options.get('font_size', 9)))
        fig.suptitle(options.get('title', 'Cycle Analysis'), fontsize=font_size + 4, fontweight='bold', y=0.988)
        show_grid = options.get('show_grid', True)
        show_legends = options.get('show_legends', False)
        style_map = {
            "Continuous (-)": "-",
            "Dashed (--)": "--",
            "Dotted (:)": ":",
            "Dash-dot (-.)": "-."
        }
        t = pd.to_numeric(aligned_df['relative_minutes'], errors='coerce').to_numpy(
            dtype=float, na_value=np.nan
        )
        finite_times = t[np.isfinite(t)]
        if not finite_times.size:
            plt.close(fig)
            return None, [], [], [], [], "The selected data has no valid elapsed-time values."

        signals_by_panel = {index: [] for index in range(n_panels)}
        for signal_id, conf in grid_widgets.items():
            if not conf['enabled'].get():
                continue

            source_col = conf.get('source_col', signal_id)
            data_col = conf.get('data_col', signal_id)
            if data_col not in aligned_df.columns:
                continue
            panel_index = panel_map[conf['panel'].get()]
            binary_col = conf.get('binary_col', f"{data_col}_BIN")
            if binary_col not in aligned_df.columns:
                binary_col = f"{data_col}_BIN"

            signal_kind = classify_signal_kind(source_col)
            is_stage = signal_kind == 'stage'
            is_digital = signal_kind in ('control', 'door_lock')
            plot_col = binary_col if is_digital and binary_col in aligned_df.columns else data_col
            col_data = aligned_df[plot_col]
            if isinstance(col_data, pd.DataFrame):
                col_data = col_data.iloc[:, 0]
            numeric_data = pd.to_numeric(col_data, errors='coerce')
            y = (
                normalize_program_stage_series(col_data).to_numpy(dtype=float)
                if is_stage else
                (normalize_control_series(col_data, source_col) if is_digital else numeric_data).to_numpy(
                    dtype=float, na_value=np.nan
                )
            )
            if is_digital:
                y = np.clip(y, 0.0, 1.0)

            try:
                line_width = float(conf['width'].get() or "1.5")
            except (TypeError, ValueError) as exc:
                plt.close(fig)
                raise ValueError(f"Line width for '{source_col}' must be a positive number.") from exc
            if not np.isfinite(line_width) or line_width <= 0:
                plt.close(fig)
                raise ValueError(f"Line width for '{source_col}' must be a positive number.")

            display_name = conf['name'].get().strip() or str(source_col)
            unit_match = re.search(r'\(([^()]+)\)\s*$', display_name)
            unit_label = unit_match.group(1).strip() if unit_match else ''
            source_clean = re.sub(r'[^a-z0-9]', ' ', str(source_col).lower()).strip()
            is_lock_state = signal_kind == 'door_lock'
            default_binary_range = (
                (not conf['ymin'].get().strip() and not conf['ymax'].get().strip())
                or (conf['ymin'].get().strip() == '0' and conf['ymax'].get().strip() == '1')
            )
            is_power = (
                not any(word in source_clean for word in ('wp', 'wh', 'kwh', 'consumed', 'energy'))
                and (
                    any(word in source_clean for word in ('p e1', 'real power', 'active power', 'wirkleistung'))
                    or source_clean == 'p'
                )
            )
            signals_by_panel[panel_index].append({
                'id': signal_id,
                'col': plot_col,
                'source_col': source_col,
                'name': display_name,
                'unit_label': unit_label,
                'unit_key': canonical_unit_key(unit_label),
                'color': conf['btn_col'].cget("bg"),
                'ls': style_map.get(conf['style'].get(), "-"),
                'lw': line_width,
                'ymin': conf['ymin'].get().strip(),
                'ymax': conf['ymax'].get().strip(),
                'is_digital': is_digital,
                'is_stage': is_stage,
                'is_lock_state': is_lock_state,
                'default_binary_range': default_binary_range,
                'side': 'right' if conf['twin'].get() else 'left',
                'is_power': is_power,
                'y': y
            })

        visible_samples = np.zeros(t.shape, dtype=bool)
        for panel_signals in signals_by_panel.values():
            for signal in panel_signals:
                visible_samples |= np.isfinite(t) & np.isfinite(signal['y'])
        visible_times = t[visible_samples] if np.any(visible_samples) else finite_times
        time_start, time_end = float(visible_times.min()), float(visible_times.max())
        axes[0].set_xlim(set_signal_time_bounds(fig, time_start, time_end))

        twin_axes_list = []
        # Keep cursor guides on the topmost signal axis in each panel so they
        # stay visible above every independently scaled trace.
        cursor_axes = list(axes)
        power_axis = None
        power_col_name = None
        layout_rows = []

        for panel_index, panel_signals in signals_by_panel.items():
            base_axis = axes[panel_index]
            if show_grid:
                base_axis.grid(True, linestyle=':', alpha=0.6)
            else:
                # Matplotlib enables the grid when style kwargs accompany
                # False, so the hidden state must be applied without them.
                base_axis.grid(False)
            base_axis.tick_params(axis='x', labelsize=font_size)
            if not panel_signals:
                continue

            # Signals with the same binary meaning share one scale. This keeps
            # repeated ON/OFF (or LOCKED/UNLOCKED) tick labels from piling up.
            axis_groups = {}
            for signal in panel_signals:
                if signal['is_digital'] and signal['default_binary_range']:
                    state_kind = 'lock' if signal['is_lock_state'] else 'on_off'
                    group_key = ('digital', signal['side'], state_kind)
                elif (
                    not signal['is_digital']
                    and signal['unit_key']
                    and not signal['ymin']
                    and not signal['ymax']
                ):
                    # Analog traces with the same unit share one numeric scale.
                    # The header legend keeps each parameter distinct.
                    group_key = ('unit', signal['side'], signal['unit_key'])
                else:
                    group_key = ('signal', signal['id'])
                axis_groups.setdefault(group_key, []).append(signal)

            panel_groups = [
                {
                    'signals': grouped_signals,
                    'side': grouped_signals[0]['side'],
                    'is_digital_group': group_key[0] == 'digital',
                    'state_kind': group_key[2] if group_key[0] == 'digital' else None,
                    'is_unit_group': group_key[0] == 'unit' and len(grouped_signals) > 1,
                    'unit_label': grouped_signals[0]['unit_label'] if group_key[0] == 'unit' else '',
                }
                for group_key, grouped_signals in axis_groups.items()
            ]
            left_groups = [group for group in panel_groups if group['side'] == 'left']
            right_groups = [group for group in panel_groups if group['side'] == 'right']

            # The subplot itself is the first axis on the selected side. Every
            # additional scale group gets a twinned axis with an offset spine.
            if left_groups:
                render_groups = [(base_axis, left_groups[0], 'left', 0)]
                remaining_left = left_groups[1:]
                right_start = 0
            else:
                render_groups = [(base_axis, right_groups[0], 'right', 0)]
                remaining_left = []
                right_start = 1

            render_groups.extend(
                (base_axis.twinx(), group, 'left', index + 1)
                for index, group in enumerate(remaining_left)
            )
            render_groups.extend(
                (base_axis.twinx(), group, 'right', index + right_start)
                for index, group in enumerate(right_groups[right_start:])
            )
            cursor_axes[panel_index] = render_groups[-1][0]

            handles, labels = [], []
            row_scales = []
            duplicate_names = {
                signal['name'] for signal in panel_signals
                if sum(other['name'] == signal['name'] for other in panel_signals) > 1
            }
            for signal_axis, group, side, offset_index in render_groups:
                grouped_signals = group['signals']
                row_scales.append({'axis': signal_axis, 'side': side})
                axis_color = '#34495E' if group['is_unit_group'] else grouped_signals[0]['color']
                axis_text_color = readable_text_color(axis_color)
                if group['is_digital_group'] and len(grouped_signals) > 1:
                    axis_name = 'Door Lock State' if group['state_kind'] == 'lock' else 'Actuator State'
                elif group['is_unit_group']:
                    axis_name = axis_title_for_unit(group['unit_label'])
                else:
                    axis_name = grouped_signals[0]['name']

                if signal_axis is not base_axis:
                    twin_axes_list.append(signal_axis)
                    signal_axis.patch.set_visible(False)
                    signal_axis.grid(False)

                spine_name = 'left' if side == 'left' else 'right'
                hidden_spine = 'right' if side == 'left' else 'left'
                signal_axis.spines[hidden_spine].set_visible(False)
                signal_axis.spines[spine_name].set_visible(True)
                signal_axis.spines[spine_name].set_position(
                    ('outward', AXIS_SPINE_GAP_POINTS * offset_index)
                )
                signal_axis.spines[spine_name].set_color(axis_color)
                signal_axis.spines[spine_name].set_linewidth(1.15)
                signal_axis.yaxis.set_label_position(side)
                signal_axis.yaxis.set_ticks_position(side)
                signal_axis.yaxis.set_major_locator(MaxNLocator(nbins=4))
                signal_axis.tick_params(axis='y', colors=axis_text_color, labelsize=font_size, pad=3)
                # Names belong in the reserved row header. Scale labels carry
                # only the unit, so long vertical names cannot hit other rows.
                scale_label = '' if group['is_digital_group'] or grouped_signals[0]['is_stage'] else grouped_signals[0]['unit_label']
                signal_axis.set_ylabel(
                    scale_label, color=axis_text_color, fontsize=font_size,
                    fontweight='bold', labelpad=4
                )

                for signal in grouped_signals:
                    if signal['is_digital']:
                        line, = signal_axis.step(
                            t, signal['y'], where='post', label=signal['name'], color=signal['color'],
                            ls=signal['ls'], lw=signal['lw'], alpha=0.86
                        )
                    elif signal['is_stage']:
                        line, = signal_axis.step(
                            t, signal['y'], where='post', label=signal['name'], color=signal['color'],
                            ls=signal['ls'], lw=signal['lw'], alpha=0.86
                        )
                        signal_axis.set_ylim(*limits_for_signal(signal))
                    else:
                        line, = signal_axis.plot(
                            t, signal['y'], label=signal['name'], color=signal['color'],
                            ls=signal['ls'], lw=signal['lw'], alpha=0.74
                        )
                        if not group['is_unit_group']:
                            signal_axis.set_ylim(*limits_for_signal(signal))

                    handles.append(line)
                    legend_label = signal['name']
                    if legend_label in duplicate_names:
                        legend_label = f"{legend_label} · {signal['source_col']}"
                    if not np.isfinite(signal['y']).any():
                        legend_label += ' · no valid samples'
                    labels.append(legend_label)
                    if signal['is_power'] and power_axis is None:
                        power_axis = signal_axis
                        power_col_name = signal['col']

                if group['is_unit_group']:
                    combined = np.concatenate([signal['y'] for signal in grouped_signals])
                    combined_limits = limits_for_signal({
                        'y': combined,
                        'name': axis_name,
                        'ymin': '',
                        'ymax': '',
                        'is_digital': False,
                    })
                    signal_axis.set_ylim(*combined_limits)

                if group['is_digital_group']:
                    signal_axis.set_ylim(-0.04, 1.04)
                    if group['state_kind'] == 'lock':
                        _set_lock_state_ticks(signal_axis, side, axis_text_color)
                    else:
                        signal_axis.set_yticks([0, 1])
                        signal_axis.set_yticklabels(
                            ['OFF', 'ON'], fontweight='bold', color=axis_text_color,
                            rotation=0, va='center', ha='center'
                        )
                        signal_axis.tick_params(axis='y', labelrotation=0)
                elif grouped_signals[0]['is_digital']:
                    signal_axis.set_ylim(*limits_for_signal(grouped_signals[0]))
                    if grouped_signals[0]['is_lock_state']:
                        _set_lock_state_ticks(signal_axis, side, axis_text_color)
                    else:
                        requested_limits = signal_axis.get_ylim()
                        signal_axis.set_yticks([0, 1])
                        signal_axis.set_yticklabels(['OFF', 'ON'], fontweight='bold')
                        signal_axis.set_ylim(requested_limits)
                elif grouped_signals[0]['is_stage']:
                    requested_limits = signal_axis.get_ylim()
                    signal_axis.set_yticks([1, 2, 3])
                    signal_axis.set_yticklabels(['1 · Wash', '2 · Rinse', '3 · Spin'], fontweight='bold')
                    signal_axis.set_ylim(requested_limits)

            unit_keys = {signal['unit_key'] for signal in panel_signals}
            if len(panel_signals) == 1:
                panel_title = panel_signals[0]['name']
            elif all(signal['is_stage'] for signal in panel_signals):
                panel_title = 'Program Stage'
            elif all(signal['is_digital'] for signal in panel_signals):
                panel_title = format_axis_title(panel_signals).replace(' (0/1)', '')
            elif len(unit_keys) == 1 and next(iter(unit_keys)):
                panel_title = axis_title_for_unit(panel_signals[0]['unit_label'])
                labels = [re.sub(r'\s+\([^()]+\)$', '', label) for label in labels]
            else:
                unit_labels = list(dict.fromkeys(signal['unit_label'] for signal in panel_signals))
                panel_title = ' · '.join(axis_title_for_unit(unit) for unit in unit_labels if unit)
                if not panel_title:
                    panel_title = f"Signals · {active_panels[panel_index]}"
            layout_rows.append({
                'axis': base_axis,
                'axes': [item[0] for item in render_groups],
                'scales': row_scales,
                'title': panel_title,
                'title_color': panel_signals[0]['color'] if len(panel_signals) == 1 else '#344054',
                'legend_entries': [(handle, label) for handle, label in zip(handles, labels)],
                'note': ('No valid samples are available for the selected signals in this block.'
                         if not any(np.isfinite(signal['y']).any() for signal in panel_signals) else ''),
            })

        # Highlight overlap in axes coordinates so it never changes a signal's
        # independently calculated y range.
        if options.get('highlight_overlap', False):
            inlet_signals, drain_signals = [], []
            for panel_index, panel_signals in signals_by_panel.items():
                for signal in panel_signals:
                    if not signal['is_digital']:
                        continue
                    name = re.sub(r'[_/-]+', ' ', f"{signal['source_col']} {signal['name']}".lower())
                    if any(word in name for word in ('drain', 'ablauf', 'abpump')):
                        drain_signals.append(signal)
                    elif any(word in name for word in (
                        'inlet', 'pre wash', 'prewash', 'main wash', 'wash valve', 'water inlet', 'zulauf'
                    )):
                        inlet_signals.append((panel_index, signal))

            if inlet_signals and drain_signals:
                drain_on = np.logical_or.reduce([signal['y'] > 0 for signal in drain_signals])
                for panel_index in dict.fromkeys(index for index, _signal in inlet_signals):
                    inlet_on = np.logical_or.reduce([
                        signal['y'] > 0 for index, signal in inlet_signals if index == panel_index
                    ])
                    overlap = inlet_on & drain_on & np.isfinite(t)
                    edges = np.flatnonzero(np.diff(np.r_[False, overlap, False]))
                    first_patch = None
                    for start, stop in zip(edges[::2], edges[1::2]):
                        end = min(stop, len(t) - 1)
                        if not np.isfinite(t[end]) or t[end] <= t[start]:
                            continue
                        patch = axes[panel_index].axvspan(
                            t[start], t[end], color='#D32F2F', alpha=0.18,
                            label='Inlet / drain overlap' if first_patch is None else '_nolegend_'
                        )
                        if first_patch is None:
                            first_patch = patch
                    if first_patch is not None:
                        layout_rows[panel_index]['legend_entries'].append(
                            (first_patch, 'Inlet / drain overlap')
                        )

        if options.get('annotate_peak', True) and power_axis is not None and power_col_name in aligned_df.columns:
            power_series = pd.to_numeric(aligned_df[power_col_name], errors='coerce')
            speed_cols = [column for column in aligned_df.columns if any(key in str(column).lower() for key in ('speed', 'rpm', 'drehzahl'))]
            actual_speed_cols = [column for column in speed_cols if not any(
                key in str(column).lower() for key in ('target', 'dest', 'dst', 'set', 'soll', 'feedback', '_bin')
            )]
            speed_cols = actual_speed_cols or speed_cols
            if speed_cols:
                speed_series = pd.to_numeric(aligned_df[speed_cols[0]], errors='coerce')
                spin_mask = (power_series >= 0) & (power_series < 1000) & (speed_series.abs() > 800)
                if spin_mask.any():
                    spin_power = power_series[spin_mask]
                    peak_power = float(spin_power.max())
                    peak_index = spin_power.idxmax()
                    peak_time = float(aligned_df.loc[peak_index, 'relative_minutes'])
                    power_axis.plot(
                        peak_time, peak_power, marker='o', color='#D32F2F',
                        markeredgecolor='white', markersize=6, zorder=8
                    )
                    power_axis.text(
                        0.015, 0.96, f'Peak Motor: {peak_power:.1f} W',
                        transform=power_axis.transAxes, ha='left', va='top',
                        fontsize=max(7, font_size - 1), color='#7F1D1D', zorder=9,
                        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#D8C99B", lw=0.7, alpha=0.9)
                    )

        c1_lines, c2_lines = [], []
        t_init = float(np.nanmin(t)) if len(t) and np.isfinite(t).any() else 0.0
        t_init_c2 = float(np.nanmedian(t)) if len(t) and np.isfinite(t).any() else 0.0
        for axis in cursor_axes:
            c1_lines.append(axis.axvline(x=t_init, color='#D32F2F', linestyle='--', linewidth=1.5, alpha=0.9))
            c2_lines.append(axis.axvline(x=t_init_c2, color='#1976D2', linestyle=':', linewidth=1.5, alpha=0.9, visible=False))

        for hook in options.get('custom_plot_hooks', []):
            try:
                hook(fig, axes, aligned_df)
            except Exception as exc:
                print(f"Plot hook warning: {exc}")

        SignalFigureLayout(
            fig, layout_rows, font_size=font_size,
            show_legends=show_legends, legend_dragger=enable_draggable_legend
        )
        fig._signal_initial_ylims = {
            axis: axis.get_ylim() for axis in axes + twin_axes_list
        }

        return fig, axes, twin_axes_list, c1_lines, c2_lines, None
