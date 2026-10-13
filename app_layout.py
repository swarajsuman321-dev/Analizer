"""Measure signal chart decorations in pixels and keep every row aligned."""

import math

from matplotlib.backends.backend_agg import RendererAgg
from matplotlib.font_manager import FontProperties
from matplotlib.transforms import Bbox
from matplotlib.colors import to_hex, to_rgb


def readable_text_color(color):
    """Keep a trace's hue while making its text legible on a white chart."""
    try:
        rgb = list(to_rgb(color))
    except ValueError:
        return '#344054'
    for _ in range(24):
        linear = [value / 12.92 if value <= 0.04045
                  else ((value + 0.055) / 1.055) ** 2.4 for value in rgb]
        luminance = sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
        if 1.05 / (luminance + 0.05) >= 4.5:
            return to_hex(rgb)
        rgb = [value * 0.9 for value in rgb]
    return '#344054'


def set_signal_time_bounds(figure, start, end):
    """Fit visible data with a small lead-in that exposes startup transitions."""
    start, end = float(start), float(end)
    if not math.isfinite(start) or not math.isfinite(end) or end < start:
        raise ValueError("Elapsed-time bounds must be finite and in increasing order.")
    figure._signal_data_time_bounds = (start, end)
    if end <= start:
        end = start + 1.0
    # Keep this deliberate margin compact even for long appliance cycles.
    lead_in = min(2.0, (end - start) * 0.015)
    figure._signal_time_bounds = (start - lead_in, end)
    return figure._signal_time_bounds


class SignalFigureLayout:
    """Responsive layout shared by dashboard and comparison figures.

    Rows keep their original axes so resizing cannot reset zoom or cursors.
    The Tk host uses the minimum content size instead of squeezing ten rows
    into the same height as one row. All sizes below are physical points.
    """

    def __init__(self, figure, rows, font_size=9, show_legends=False,
                 legend_dragger=None):
        if not rows:
            raise ValueError("A signal figure needs at least one visible block.")
        previous = getattr(figure, '_signal_layout', None)
        if previous is not None and hasattr(previous, 'dispose'):
            previous.dispose(remove_artists=True)
        self.figure = figure
        self.rows = rows
        self.font_size = max(8, min(16, float(font_size)))
        self.show_legends = bool(show_legends)
        self.legend_dragger = legend_dragger
        self._busy = False
        self._disposed = False
        self._last_fingerprint = None
        self._pressed_legend = None
        self.on_size_change = None
        self._required_size = None
        self._left_extent = 55.0
        self._right_extent = 20.0
        figure._signal_layout = self
        figure._signal_legends = []
        for row in rows:
            row.setdefault('axes', [row['axis']])
            row.setdefault('scales', [{'axis': row['axis'], 'side': 'left'}])
            row.setdefault('legend_entries', [])
            row['heading'] = figure.text(
                0, 0, row.get('title', ''), ha='left', va='top',
                fontsize=self.font_size, fontweight='bold',
                color=readable_text_color(row.get('title_color', '#344054'))
            )
            row['legend'] = None
            row['legend_config'] = None
            row['legend_moved'] = False
            row['note_artist'] = figure.text(
                0, 0, row.get('note', ''), ha='left', va='top',
                fontsize=max(8, self.font_size - 1), color='#596579'
            )
            for axis in row['axes']:
                axis.set_in_layout(False)
                axis.tick_params(axis='x', labelsize=max(8, self.font_size - 1), pad=3)
                axis.tick_params(axis='y', labelsize=self.font_size, pad=3)
            # Repeat the shared time ticks so a scrolled block can be read on
            # its own. Every row still uses exactly the same elapsed-time range.
            row['axis'].tick_params(axis='x', labelbottom=True)

        self.x_label = rows[-1]['axis'].xaxis.label
        self.x_label.set_text('Elapsed Time (Minutes)')
        self.x_label.set_fontsize(self.font_size + 1)
        self.x_label.set_fontweight('bold')
        self.x_label.set_verticalalignment('bottom')
        self.x_label.set_horizontalalignment('center')
        self._connection_ids = [
            figure.canvas.mpl_connect('resize_event', self._on_resize),
            figure.canvas.mpl_connect('draw_event', self._on_draw),
            figure.canvas.mpl_connect('button_press_event', self._on_press),
            figure.canvas.mpl_connect('button_release_event', self._on_release),
        ]
        self.reflow()

    def dispose(self, remove_artists=False):
        """Detach callbacks when a chart host is destroyed or replaced."""
        if self._disposed:
            return
        self._disposed = True
        self.on_size_change = None
        self._pressed_legend = None
        for connection_id in self._connection_ids:
            self.figure.canvas.mpl_disconnect(connection_id)
        self._connection_ids.clear()
        for row in self.rows:
            legend = row.get('legend')
            if legend is not None:
                self._disconnect_legend(legend)
            if remove_artists:
                for artist in (row.get('heading'), row.get('note_artist'), legend):
                    if artist is not None:
                        artist.remove()
        if getattr(self.figure, '_signal_layout', None) is self:
            self.figure._signal_layout = None
            self.figure._signal_legends = []

    def _disconnect_legend(self, legend):
        legend._signal_drag_disposed = True
        press_cid = getattr(legend, '_signal_drag_press_cid', None)
        if press_cid is not None:
            self.figure.canvas.mpl_disconnect(press_cid)
            legend._signal_drag_press_cid = None
        legend.set_draggable(False)

    def _pixels(self, points):
        return points * self.figure.dpi / 72.0

    def _renderer(self):
        try:
            return self.figure.canvas.get_renderer()
        except (AttributeError, RuntimeError):
            return RendererAgg(
                max(1, int(self.figure.bbox.width)),
                max(1, int(self.figure.bbox.height)), self.figure.dpi
            )

    def _text_width(self, text, renderer, size=None):
        props = FontProperties(size=size or self.font_size)
        return max((renderer.get_text_width_height_descent(
            line, props, ismath=False
        )[0] for line in str(text).splitlines()), default=0)

    def _wrap(self, text, width, renderer, size=None):
        words = str(text).replace('\n', ' ').split()
        lines, current = [], ''
        for word in words:
            if self._text_width(word, renderer, size) > width:
                if current:
                    lines.append(current)
                    current = ''
                chunk = ''
                for character in word:
                    if chunk and self._text_width(chunk + character, renderer, size) > width:
                        lines.append(chunk)
                        chunk = character
                    else:
                        chunk += character
                current = chunk
                continue
            candidate = f'{current} {word}'.strip()
            if current and self._text_width(candidate, renderer, size) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return '\n'.join(lines)

    def _measure_scales(self, renderer):
        left_extent = right_extent = 0.0
        for row in self.rows:
            for side in ('left', 'right'):
                offset = 0.0
                for scale in (item for item in row['scales'] if item['side'] == side):
                    axis = scale['axis']
                    axis.spines[side].set_position(('outward', offset * 72.0 / self.figure.dpi))
                    self._align_rotated_ticks(axis, renderer)
                    box = axis.yaxis.get_tightbbox(renderer)
                    icon_boxes = [item[0] for item in self._state_icon_boxes(axis, renderer)]
                    boxes = ([box] if box is not None else []) + icon_boxes
                    box = Bbox.union(boxes) if boxes else None
                    plot_box = axis.get_window_extent(renderer)
                    if box is None:
                        width = self._pixels(24)
                    elif side == 'left':
                        width = max(0.0, plot_box.x0 - offset - box.x0)
                    else:
                        width = max(0.0, box.x1 - plot_box.x1 - offset)
                    extent = offset + width
                    if side == 'left':
                        left_extent = max(left_extent, extent)
                    else:
                        right_extent = max(right_extent, extent)
                    offset += width + self._pixels(8)
        self._left_extent = left_extent
        self._right_extent = right_extent
        return left_extent, right_extent

    @staticmethod
    def _visible_y_ticks(axis):
        lower, upper = sorted(axis.get_ylim())
        tolerance = max(1.0, upper - lower) * 1e-9
        return [tick for tick in axis.yaxis.get_major_ticks()
                if lower - tolerance <= tick.get_loc() <= upper + tolerance]

    def _align_rotated_ticks(self, axis, renderer):
        # Moving a spine recreates tick objects, so apply these anchors after
        # every move. Endpoint text points into the block instead of extending
        # into its neighbour; centered interior ticks retain their own space.
        axis.yaxis.get_tightbbox(renderer)
        ticks = sorted(self._visible_y_ticks(axis), key=lambda tick: tick.get_loc())
        inverted = axis.yaxis_inverted()
        for index, tick in enumerate(ticks):
            for label in (tick.label1, tick.label2):
                if not label.get_visible() or abs(label.get_rotation() % 360 - 90) > 1e-6:
                    continue
                label.set_rotation_mode('anchor')
                label.set_verticalalignment('center')
                alignment = 'center'
                if len(ticks) > 1:
                    if index == 0:
                        alignment = 'right' if inverted else 'left'
                    elif index == len(ticks) - 1:
                        alignment = 'left' if inverted else 'right'
                label.set_horizontalalignment(alignment)

    def _state_icon_boxes(self, axis, renderer):
        boxes = []
        lower, upper = sorted(axis.get_ylim())
        for icon in getattr(axis, '_signal_state_icons', []):
            artist = icon['artist']
            visible = lower <= icon['value'] <= upper
            artist.set_visible(visible)
            if not visible:
                continue
            which = 'tick1' if icon['side'] == 'left' else 'tick2'
            # Spine moves replace its transform; refresh the annotation too.
            artist.xycoords = axis.get_yaxis_transform(which=which)
            artist.update_positions(renderer)
            anchor_y = artist.xycoords.transform(artist.xy)[1]
            boxes.append((artist.get_window_extent(renderer), anchor_y))
        return boxes

    def _scale_label_boxes(self, axis, renderer, include_axis_text=False):
        axis.yaxis.get_tightbbox(renderer)
        texts = [label for tick in self._visible_y_ticks(axis)
                 for label in (tick.label1, tick.label2)]
        if include_axis_text:
            texts.extend((axis.yaxis.label, axis.yaxis.get_offset_text()))
        boxes = []
        for artist in texts:
            if artist.get_visible() and artist.get_text():
                anchor_y = artist.get_transform().transform(artist.get_position())[1]
                boxes.append((artist.get_window_extent(renderer), anchor_y))
        return boxes + self._state_icon_boxes(axis, renderer)

    def _vertical_scale_overhang(self, row, body_height, renderer):
        """Predict decoration bounds at the minimum readable block height."""
        above = below = 0.0
        for scale in row['scales']:
            axis = scale['axis']
            plot = axis.get_window_extent(renderer)
            for box, anchor_y in self._scale_label_boxes(axis, renderer, include_axis_text=True):
                relative_y = anchor_y - plot.y0
                if relative_y < 0:
                    resized_y = relative_y
                elif relative_y > plot.height:
                    resized_y = body_height + relative_y - plot.height
                else:
                    resized_y = relative_y * body_height / max(1.0, plot.height)
                predicted_bottom = box.y0 - anchor_y + resized_y
                predicted_top = box.y1 - anchor_y + resized_y
                below = max(below, -predicted_bottom)
                above = max(above, predicted_top - body_height)
        return above, below

    def _minimum_tick_body(self, row, body_height, renderer):
        """Reserve space between labels that occupy the same scale column."""
        labels = []
        for scale in row['scales']:
            axis = scale['axis']
            plot = axis.get_window_extent(renderer)
            for box, anchor_y in self._scale_label_boxes(axis, renderer):
                fraction = min(1.0, max(0.0,
                    (anchor_y - plot.y0) / max(1.0, plot.height)))
                # Preserve any fixed pixel offset beyond an endpoint.
                anchor_offset = anchor_y - (plot.y0 + fraction * plot.height)
                labels.append((fraction, box.y0 - anchor_y + anchor_offset,
                               box.y1 - anchor_y + anchor_offset, box.x0, box.x1))

        labels.sort(key=lambda item: item[0])
        gap = self._pixels(6)
        for index, lower in enumerate(labels):
            for upper in labels[index + 1:]:
                separation = upper[0] - lower[0]
                if separation <= 1e-9:
                    continue
                if lower[4] <= upper[3] or upper[4] <= lower[3]:
                    continue
                # The lower word can extend upward and the upper word down.
                # Both extents, rather than just the larger one, must fit.
                body_height = max(body_height,
                                  (lower[2] - upper[1] + gap) / separation)
        return body_height

    def minimum_width(self):
        self._measure_scales(self._renderer())
        return int(math.ceil(
            self._left_extent + self._right_extent + self._pixels(330 + 20)
        ))

    def _make_legend(self, row, labels, columns):
        old = row.get('legend')
        if old is not None:
            self._disconnect_legend(old)
            old.remove()
        entries = row['legend_entries']
        legend = row['axes'][-1].legend(
            [entry[0] for entry in entries], labels,
            loc='upper right', bbox_to_anchor=(1, 1),
            bbox_transform=self.figure.transFigure,
            borderaxespad=0, fontsize=self.font_size,
            ncol=columns, frameon=True, framealpha=0.97,
            facecolor='white', edgecolor='#D8E0E8',
            handlelength=1.8, handletextpad=0.5,
            columnspacing=1.0, labelspacing=0.35, borderpad=0.4
        )
        # Swatches identify the line colors; neutral text remains readable even
        # when the user chooses yellow or another light trace color.
        for text in legend.get_texts():
            text.set_color('#344054')
        row['legend'] = legend
        row['legend_config'] = (tuple(labels), columns)
        if self.legend_dragger:
            self.legend_dragger(legend)
        else:
            legend.set_draggable(True)
        return legend

    def _measure_header(self, row, width, renderer):
        heading = row['heading']
        heading.set_text(self._wrap(row.get('title', ''), width, renderer))
        title_box = heading.get_window_extent(renderer)
        title_width, title_height = title_box.width, title_box.height
        entries = row['legend_entries']
        visible = bool(entries) and (self.show_legends or len(entries) > 1)
        legend = row.get('legend')
        if not visible:
            if legend is not None:
                legend.set_visible(False)
            return {'height': title_height + self._pixels(5), 'stacked': False}

        labels = [self._wrap(entry[1], min(width - self._pixels(40), self._pixels(195)),
                             renderer) for entry in entries]
        # Estimate the columns first, so ordinary redraws reuse the same legend
        # and its drag callbacks instead of rebuilding every candidate.
        item_widths = [self._text_width(label, renderer) + self._pixels(26)
                       for label in labels]
        previous_config = row.get('legend_config')
        fitted_before = (
            previous_config is not None and previous_config[0] == tuple(labels)
            and abs(row.get('legend_fit_width', -1) - width) < 1
        )
        columns = previous_config[1] if fitted_before else 1
        for candidate in ([] if fitted_before else range(min(4, len(entries)), 0, -1)):
            quotient, remainder = divmod(len(entries), candidate)
            start, column_widths = 0, []
            for column in range(candidate):
                count = quotient + (column < remainder)
                column_widths.append(max(item_widths[start:start + count]))
                start += count
            estimated = sum(column_widths) + self._pixels(9 * (candidate - 1) + 8)
            if estimated <= width - self._pixels(3):
                columns = candidate
                break
        while True:
            config = (tuple(labels), columns)
            if row.get('legend_config') != config:
                legend = self._make_legend(row, labels, columns)
            else:
                legend = row['legend']
            legend.set_visible(True)
            box = legend.get_window_extent(renderer)
            if box.width <= width - self._pixels(3) or columns == 1:
                break
            columns -= 1

        legend_width, legend_height = box.width, box.height
        row['legend_fit_width'] = width
        stacked = title_width + legend_width + self._pixels(12) > width
        height = (title_height + legend_height + self._pixels(8) if stacked
                  else max(title_height, legend_height) + self._pixels(5))
        return {'height': height, 'stacked': stacked, 'title_height': title_height,
                'legend_width': legend_width, 'legend_height': legend_height}

    def _measure(self, width_px):
        renderer = self._renderer()
        left_extent, right_extent = self._measure_scales(renderer)
        outer = self._pixels(10)
        left, right = outer + left_extent, width_px - outer - right_extent
        plot_width = max(self._pixels(180), right - left)
        headers = [self._measure_header(row, plot_width, renderer) for row in self.rows]
        note_heights = []
        for row in self.rows:
            note = row['note_artist']
            note.set_text(self._wrap(row.get('note', ''), plot_width, renderer,
                                     note.get_fontsize()))
            note.set_visible(bool(row.get('note')))
            note_heights.append(
                note.get_window_extent(renderer).height + self._pixels(4)
                if note.get_visible() else 0.0
            )
        tick_heights = []
        min_bodies = []
        for row in self.rows:
            ticks = [tick for tick in row['axis'].get_xticklabels() if tick.get_visible()]
            tick_height = max((tick.get_window_extent(renderer).height for tick in ticks), default=0)
            tick_heights.append(tick_height + self._pixels(7))
            y_text_height = max((
                tick.get_window_extent(renderer).height
                for axis in row['axes'] for tick in axis.get_yticklabels()
                if tick.get_visible()
            ), default=0)
            min_bodies.append(max(self._pixels(68), y_text_height + self._pixels(28)))

        # Tick heights alone miss rotated state text and long scale labels.
        # Reserve their overhang in the header/footer using the smallest body
        # this row can receive, keeping the spacing valid after any resize.
        for index, (row, body) in enumerate(zip(self.rows, min_bodies)):
            body = self._minimum_tick_body(row, body, renderer)
            min_bodies[index] = body
            above, below = self._vertical_scale_overhang(row, body, renderer)
            headers[index]['height'] = max(headers[index]['height'], above + self._pixels(4))
            tick_heights[index] = max(tick_heights[index], below + self._pixels(4))

        label_height = self.x_label.get_window_extent(renderer).height
        title = self.figure._suptitle
        title_height = 0.0
        if title is not None:
            title.set_text(self._wrap(getattr(self, '_title', title.get_text()), plot_width,
                                      renderer, title.get_fontsize()))
            self._title = getattr(self, '_title', title.get_text().replace('\n', ' '))
            title_height = title.get_window_extent(renderer).height
        top = title_height + self._pixels(18)
        bottom = label_height + self._pixels(12)
        gaps = self._pixels(9) * max(0, len(self.rows) - 1)
        minimum = top + bottom + gaps + sum(
            header['height'] + body + ticks + note
            for header, body, ticks, note in zip(headers, min_bodies, tick_heights, note_heights)
        )
        self.figure._signal_legends = [row['legend'] for row in self.rows if row.get('legend')]
        return left, right, headers, min_bodies, tick_heights, note_heights, top, bottom, minimum

    def minimum_height(self, width_px=None):
        width_px = float(width_px or self.figure.bbox.width)
        return int(math.ceil(self._measure(width_px)[-1]))

    def set_show_legends(self, show):
        if self._disposed:
            return
        self.show_legends = bool(show)
        self.reflow()

    def reflow(self, width_px=None, height_px=None):
        if self._busy or self._disposed or not self.rows:
            return
        self._busy = True
        try:
            width = float(width_px or self.figure.bbox.width)
            height = float(height_px or self.figure.bbox.height)
            (left, right, headers, minimum_bodies, tick_heights, note_heights,
             top, bottom, minimum) = self._measure(width)
            extra_per_row = max(0.0, height - minimum) / len(self.rows)
            cursor_top = height - top
            for row, header, minimum_body, ticks, note_height in zip(
                    self.rows, headers, minimum_bodies, tick_heights, note_heights):
                body_height = minimum_body + extra_per_row
                header_top = cursor_top
                body_top = header_top - header['height']
                body_bottom = body_top - body_height
                position = Bbox.from_bounds(
                    left / width, body_bottom / height,
                    max(1, right - left) / width, body_height / height
                )
                for axis in row['axes']:
                    axis.set_position(position)
                row['heading'].set_position((left / width, header_top / height))
                legend = row.get('legend')
                if legend is not None and legend.get_visible():
                    if row['legend_moved']:
                        # Recreate with a public loc/anchor pair; native dragging
                        # stores a free offset that otherwise drifts after resize.
                        anchor = row['legend_anchor']
                        if hasattr(legend, 'set_loc'):
                            legend.set_loc('upper right')
                        else:
                            labels, columns = row['legend_config']
                            legend = self._make_legend(row, list(labels), columns)
                        box = legend.get_window_extent(self._renderer())
                        anchor_x = left + anchor[0] * (right - left)
                        anchor_y = body_bottom + anchor[1] * body_height
                        outer = self._pixels(6)
                        anchor_x = min(width - outer, max(box.width + outer, anchor_x))
                        anchor_y = min(height - outer, max(box.height + outer, anchor_y))
                        legend.set_bbox_to_anchor(
                            (anchor_x / width, anchor_y / height),
                            transform=self.figure.transFigure
                        )
                    else:
                        legend_top = header_top
                        if header['stacked']:
                            legend_top -= header['title_height'] + self._pixels(3)
                        legend.set_bbox_to_anchor(
                            (right / width, legend_top / height),
                            transform=self.figure.transFigure
                        )
                row['note_artist'].set_position((left / width, (body_bottom - ticks) / height))
                cursor_top = body_bottom - ticks - note_height - self._pixels(9)

            if self.figure._suptitle is not None:
                self.figure._suptitle.set_position(((left + right) / (2 * width),
                                                    1 - self._pixels(8) / height))
                self.figure._suptitle.set_verticalalignment('top')
            self.rows[-1]['axis'].xaxis.set_label_coords(
                (left + right) / (2 * width), self._pixels(9) / height,
                transform=self.figure.transFigure
            )
            self._last_fingerprint = self._fingerprint()
            required_size = (
                int(math.ceil(self._left_extent + self._right_extent + self._pixels(350))),
                int(math.ceil(minimum))
            )
            if required_size != self._required_size:
                self._required_size = required_size
                if callable(self.on_size_change):
                    self.on_size_change()
        finally:
            self._busy = False

    def _fingerprint(self):
        return (round(self.figure.bbox.width), round(self.figure.bbox.height),
                self.figure.dpi, self.show_legends,
                tuple((axis.get_xlim(), axis.get_ylim())
                      for row in self.rows for axis in row['axes']))

    def _on_resize(self, _event):
        self.reflow()

    def _on_draw(self, _event):
        if not self._disposed and not self._busy and self._fingerprint() != self._last_fingerprint:
            self.reflow()
            self.figure.canvas.draw_idle()

    def _on_press(self, event):
        self._pressed_legend = None
        if self._disposed or event.button != 1:
            return
        renderer = self._renderer()
        for row in self.rows:
            legend = row.get('legend')
            if legend is not None and legend.get_visible() and legend.contains(event)[0]:
                self._pressed_legend = (row, legend.get_window_extent(renderer).frozen())
                break

    def _on_release(self, _event):
        if self._disposed or self._pressed_legend is None:
            return
        row, before = self._pressed_legend
        self._pressed_legend = None
        legend = row['legend']
        if legend is None or not legend.get_visible():
            return
        box = legend.get_window_extent(self._renderer())
        if abs(box.x0 - before.x0) + abs(box.y0 - before.y0) < 2:
            return
        axis_box = row['axis'].get_window_extent()
        row['legend_moved'] = True
        row['legend_anchor'] = (
            (box.x1 - axis_box.x0) / max(1, axis_box.width),
            (box.y1 - axis_box.y0) / max(1, axis_box.height)
        )
