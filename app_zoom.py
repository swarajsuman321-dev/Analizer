import tkinter as tk
import matplotlib.patches as patches
import numpy as np

def views_differ(v1, v2):
    if v1 is None or v2 is None:
        return False
    x1, y1, ty1 = v1
    x2, y2, ty2 = v2
    if abs(x1[0] - x2[0]) > 1e-5 or abs(x1[1] - x2[1]) > 1e-5:
        return True
    for ax in y1:
        if ax in y2:
            if abs(y1[ax][0] - y2[ax][0]) > 1e-5 or abs(y1[ax][1] - y2[ax][1]) > 1e-5:
                return True
    for tax in ty1:
        if tax in ty2:
            if abs(ty1[tax][0] - ty2[tax][0]) > 1e-5 or abs(ty1[tax][1] - ty2[tax][1]) > 1e-5:
                return True
    return False

class ZoomInteractionManager:
    def __init__(self, canvas, axes, twin_axes=None, c1_lines=None, c2_lines=None,
                 on_cursor_change=None, on_hover=None, on_export_excel=None,
                 on_export_image=None, on_export_csv=None):
        self.canvas = canvas
        self._disposed = False
        self.axes = axes
        self.twin_axes = twin_axes or []
        self.c1_lines = c1_lines or []
        self.c2_lines = c2_lines or []
        self.on_cursor_change = on_cursor_change
        self.on_hover = on_hover
        self.on_export_excel = on_export_excel
        self.on_export_image = on_export_image
        self.on_export_csv = on_export_csv

        self.mode = "CURSOR"
        self.dual_cursor_active = False
        self.active_cursor_target = "C1"

        self.history_views = []
        self.forward_views = []
        self._pending_view = None

        self.dragging_cursor = None
        self.panning = False
        self.pan_start_display_x = None
        self.pan_start_display_y = None
        self.pan_target_ax = None
        self.pan_start_xlim = None
        self.pan_start_ylims = {}

        self.zoom_start_x = None
        self.zoom_start_y = None
        self.zoom_ax = None
        self.preview_patches = []
        self._context_menu = None

        self.initial_xlim = None
        self.initial_ylims = {}
        self.initial_twin_ylims = {}
        self._record_initial_limits()

        self.cid_press = self.canvas.mpl_connect('button_press_event', self.on_press)
        self.cid_motion = self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.cid_release = self.canvas.mpl_connect('button_release_event', self.on_release)
        self.cid_scroll = self.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.cid_close = self.canvas.mpl_connect('close_event', lambda _event: self.dispose())

    def dispose(self):
        """Release event handlers and references when the figure is replaced."""
        if self._disposed:
            return
        self._disposed = True
        for connection_id in (self.cid_press, self.cid_motion, self.cid_release,
                              self.cid_scroll, self.cid_close):
            self.canvas.mpl_disconnect(connection_id)
        self._clear_preview_patches()
        self.dragging_cursor = None
        self.panning = False
        self.zoom_ax = self.pan_target_ax = None
        self._pending_view = None
        self.history_views.clear()
        self.forward_views.clear()
        self.on_cursor_change = self.on_hover = None
        self.on_export_excel = self.on_export_image = self.on_export_csv = None
        if self._context_menu is not None:
            try:
                self._context_menu.destroy()
            except tk.TclError:
                pass
            self._context_menu = None

    @staticmethod
    def _push_view(destination, view):
        if view is not None and (not destination or views_differ(destination[-1], view)):
            destination.append(view)
            # A long inspection session should not retain unlimited snapshots.
            del destination[:-200]

    def _record_initial_limits(self):
        if self.axes and len(self.axes) > 0:
            # Visibility changes recreate the interaction manager after the
            # current zoom is restored. Fit must still show the full view domain,
            # including the small lead-in that makes startup transitions visible.
            self.initial_xlim = self._time_bounds() or self.axes[0].get_xlim()
            self._set_time_xlim(self.axes[0].get_xlim())
            fitted_ylims = getattr(self.canvas.figure, '_signal_initial_ylims', {})
            for ax in self.axes:
                self.initial_ylims[ax] = fitted_ylims.get(ax, ax.get_ylim())
            for tax in self.twin_axes:
                self.initial_twin_ylims[tax] = fitted_ylims.get(tax, tax.get_ylim())

    def _time_bounds(self):
        """Return the allowed view domain, including its intentional lead-in."""
        bounds = getattr(self.canvas.figure, '_signal_time_bounds', None)
        try:
            left, right = map(float, bounds)
        except (TypeError, ValueError):
            return None
        if np.isfinite(left) and np.isfinite(right) and right > left:
            return left, right
        return None

    def _bounded_time_xlim(self, limits):
        """Keep a zoom's width while shifting it inside the allowed view domain."""
        bounds = self._time_bounds()
        if bounds is None:
            return limits
        left, right = map(float, limits)
        if not np.isfinite(left) or not np.isfinite(right):
            return bounds
        reversed_axis = left > right
        left, right = sorted((left, right))
        width = right - left
        start, end = bounds
        if width <= 0 or width >= end - start:
            result = bounds
        else:
            left = max(start, min(left, end - width))
            result = left, left + width
        return result[::-1] if reversed_axis else result

    def _set_time_xlim(self, limits):
        limits = self._bounded_time_xlim(limits)
        for axis in self.axes:
            axis.set_xlim(limits)
        return limits

    def _get_current_view(self):
        if not self.axes:
            return None
        xlim = self.axes[0].get_xlim()
        ylims = {ax: ax.get_ylim() for ax in self.axes}
        twin_ylims = {tax: tax.get_ylim() for tax in self.twin_axes}
        return (xlim, ylims, twin_ylims)

    def set_mode(self, mode):
        if mode not in ('CURSOR', 'HAND', 'ZOOM_X', 'ZOOM_Y', 'ZOOM_XY'):
            raise ValueError(f"Unknown graph interaction mode: {mode}")
        self.mode = mode
        self.dragging_cursor = None
        self.panning = False
        self.zoom_start_x = self.zoom_start_y = None
        self.zoom_ax = self.pan_target_ax = None
        self.pan_start_display_x = self.pan_start_display_y = None
        self._pending_view = None
        self._clear_preview_patches()
        if not self._disposed:
            self.canvas.draw_idle()

    def set_active_cursor_target(self, target):
        if target not in ('C1', 'C2'):
            raise ValueError("Select cursor C1 or C2.")
        self.active_cursor_target = target

    def toggle_dual_cursor(self):
        if self._disposed:
            return
        self.dual_cursor_active = not self.dual_cursor_active
        for l2 in self.c2_lines:
            l2.set_visible(self.dual_cursor_active)
        self.canvas.draw_idle()
        if self.on_cursor_change:
            self.on_cursor_change()

    def _cursor_time(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(value):
            return None
        bounds = getattr(self.canvas.figure, '_signal_data_time_bounds', None)
        if bounds is not None:
            try:
                start, end = map(float, bounds)
                if np.isfinite(start) and np.isfinite(end) and end >= start:
                    value = min(end, max(start, value))
            except (TypeError, ValueError):
                pass
        return value

    def _event_time(self, event):
        if event.xdata is not None:
            return event.xdata
        if self.axes and event.x is not None:
            return self.axes[0].transData.inverted().transform((event.x, event.y or 0))[0]
        return None

    def _set_c1_time(self, t_val):
        t_val = self._cursor_time(t_val)
        if self._disposed or t_val is None:
            return
        for l1 in self.c1_lines:
            l1.set_xdata([t_val, t_val])
            l1.set_visible(True)
        self.canvas.draw_idle()
        if self.on_cursor_change:
            self.on_cursor_change()

    def _set_c2_time(self, t_val):
        t_val = self._cursor_time(t_val)
        if self._disposed or t_val is None:
            return
        for l2 in self.c2_lines:
            l2.set_xdata([t_val, t_val])
            l2.set_visible(True)
        self.canvas.draw_idle()
        if self.on_cursor_change:
            self.on_cursor_change()

    def _set_c2_time_and_activate(self, t_val):
        if not self.dual_cursor_active:
            self.dual_cursor_active = True
            for l2 in self.c2_lines:
                l2.set_visible(True)
        self._set_c2_time(t_val)

    def zoom_back(self):
        if self._disposed or not self.history_views:
            return
        current_view = self._get_current_view()
        self._push_view(self.forward_views, current_view)
        prev_view = self.history_views.pop()
        xlim, ylims, twin_ylims = prev_view
        self._set_time_xlim(xlim)
        for ax in self.axes:
            if ax in ylims:
                ax.set_ylim(ylims[ax])
        for tax in self.twin_axes:
            if tax in twin_ylims:
                tax.set_ylim(twin_ylims[tax])
        self.canvas.draw_idle()

    def zoom_forward(self):
        if self._disposed or not self.forward_views:
            return
        current_view = self._get_current_view()
        self._push_view(self.history_views, current_view)
        next_view = self.forward_views.pop()
        xlim, ylims, twin_ylims = next_view
        self._set_time_xlim(xlim)
        for ax in self.axes:
            if ax in ylims:
                ax.set_ylim(ylims[ax])
        for tax in self.twin_axes:
            if tax in twin_ylims:
                tax.set_ylim(twin_ylims[tax])
        self.canvas.draw_idle()

    def reset_zoom(self):
        if not self._disposed and self.initial_xlim and self.axes:
            current_view = self._get_current_view()
            if not self.history_views or views_differ(self.history_views[-1], current_view):
                self._push_view(self.history_views, current_view)
                self.forward_views.clear()

            self._set_time_xlim(self.initial_xlim)
            for ax in self.axes:
                if ax in self.initial_ylims:
                    ax.set_ylim(self.initial_ylims[ax])
            for tax in self.twin_axes:
                if tax in self.initial_twin_ylims:
                    tax.set_ylim(self.initial_twin_ylims[tax])
            self.canvas.draw_idle()

    def _is_event_on_legend(self, event):
        all_axes = list(self.axes or []) + list(self.twin_axes or [])
        legends = list(getattr(self.canvas.figure, '_signal_legends', []))
        legends.extend(ax.get_legend() for ax in all_axes)
        for leg in dict.fromkeys(legends):
            if leg and leg.get_visible():
                try:
                    contains, _ = leg.contains(event)
                    if contains:
                        return True
                except Exception:
                    pass
        return False

    def on_press(self, event):
        if self._disposed:
            return
        if event.button == 3:
            if self.zoom_start_x is not None or self.zoom_start_y is not None:
                self._clear_preview_patches()
                self.zoom_start_x = None
                self.zoom_start_y = None
                self.zoom_ax = None
                self._pending_view = None
                self.canvas.draw_idle()
                return
            self._show_context_menu(event)
            return

        if self._is_event_on_legend(event):
            return

        if event.inaxes not in self.axes + self.twin_axes or event.button != 1:
            return

        self._pending_view = self._get_current_view()

        if self.mode == "CURSOR":
            x_click = event.xdata
            if x_click is None:
                return

            if self.dual_cursor_active and len(self.c1_lines) > 0 and len(self.c2_lines) > 0:
                t1 = float(self.c1_lines[0].get_xdata()[0])
                t2 = float(self.c2_lines[0].get_xdata()[0])
                d1 = abs(x_click - t1)
                d2 = abs(x_click - t2)
                span = abs(self.axes[0].get_xlim()[1] - self.axes[0].get_xlim()[0])
                if self.active_cursor_target == "C2" or (d2 < d1 and d2 < span * 0.05):
                    self.dragging_cursor = "C2"
                    self._set_c2_time(x_click)
                else:
                    self.dragging_cursor = "C1"
                    self._set_c1_time(x_click)
            else:
                self.dragging_cursor = "C1"
                self._set_c1_time(x_click)

        elif self.mode == "HAND":
            target_ax = event.inaxes
            self.panning = True
            self.pan_start_display_x = event.x
            self.pan_start_display_y = event.y
            self.pan_target_ax = target_ax
            self.pan_start_xlim = self.axes[0].get_xlim()
            self.pan_start_ylims = {
                ax: ax.get_ylim() for ax in list(self.axes) + list(self.twin_axes)
            }

        elif self.mode in ["ZOOM_X", "ZOOM_Y", "ZOOM_XY"]:
            target_ax = event.inaxes
            self.zoom_start_x = event.xdata
            self.zoom_start_y = event.ydata
            self.zoom_ax = target_ax
            self.pan_start_ylims = {
                ax: ax.get_ylim() for ax in list(self.axes) + list(self.twin_axes)
            }
            self._clear_preview_patches()

    def on_motion(self, event):
        if self._disposed:
            return
        if event.inaxes in self.axes + self.twin_axes and event.xdata is not None:
            if self.on_hover:
                self.on_hover(event.xdata, event.ydata)

        if self.mode == "CURSOR" and self.dragging_cursor is not None:
            new_x = self._event_time(event)
            if new_x is not None:
                if self.dragging_cursor == "C1":
                    self._set_c1_time(new_x)
                elif self.dragging_cursor == "C2":
                    self._set_c2_time(new_x)

        elif self.mode == "HAND" and self.panning and self.pan_start_display_x is not None and self.pan_target_ax is not None:
            dx_pix = event.x - self.pan_start_display_x
            dy_pix = event.y - self.pan_start_display_y

            if dx_pix != 0:
                w_pix = self.pan_target_ax.bbox.width
                if w_pix > 0:
                    x_span = self.pan_start_xlim[1] - self.pan_start_xlim[0]
                    dx_data = (x_span / w_pix) * dx_pix
                    new_xlim = (self.pan_start_xlim[0] - dx_data, self.pan_start_xlim[1] - dx_data)
                    self._set_time_xlim(new_xlim)

            if dy_pix != 0:
                h_pix = self.pan_target_ax.bbox.height
                if h_pix > 0:
                    orig_ylim = self.pan_start_ylims.get(self.pan_target_ax)
                    if orig_ylim:
                        y_span = orig_ylim[1] - orig_ylim[0]
                        dy_data = (y_span / h_pix) * dy_pix
                        self.pan_target_ax.set_ylim(orig_ylim[0] - dy_data, orig_ylim[1] - dy_data)

            self.canvas.draw_idle()

        elif self.mode in ["ZOOM_X", "ZOOM_Y", "ZOOM_XY"] and self.zoom_ax is not None:
            self._update_zoom_preview(event)

    def _update_zoom_preview(self, event):
        self._clear_preview_patches()
        if event.inaxes is None:
            return

        y_end_in_zoom_axes = None
        if self.zoom_ax is not None and event.x is not None and event.y is not None:
            try:
                y_end_in_zoom_axes = self.zoom_ax.transData.inverted().transform((event.x, event.y))[1]
            except Exception:
                y_end_in_zoom_axes = event.ydata

        if self.mode == "ZOOM_X" and self.zoom_start_x is not None and event.xdata is not None:
            x0, x1 = sorted([self.zoom_start_x, event.xdata])
            for ax in self.axes:
                span_patch = ax.axvspan(x0, x1, color='#1976D2', alpha=0.22, linestyle='--', edgecolor='#0D47A1')
                self.preview_patches.append(span_patch)
            self.canvas.draw_idle()

        elif self.mode == "ZOOM_Y" and self.zoom_start_y is not None and y_end_in_zoom_axes is not None:
            y0, y1 = sorted([self.zoom_start_y, y_end_in_zoom_axes])
            span_patch = self.zoom_ax.axhspan(y0, y1, color='#1976D2', alpha=0.22, linestyle='--', edgecolor='#0D47A1')
            self.preview_patches.append(span_patch)
            self.canvas.draw_idle()

        elif self.mode == "ZOOM_XY" and self.zoom_start_x is not None and self.zoom_start_y is not None and event.xdata is not None and y_end_in_zoom_axes is not None:
            x0, x1 = sorted([self.zoom_start_x, event.xdata])
            y0, y1 = sorted([self.zoom_start_y, y_end_in_zoom_axes])
            rect = patches.Rectangle(
                (x0, y0), x1 - x0, y1 - y0,
                facecolor='#1976D2', alpha=0.22, edgecolor='#0D47A1', linestyle='--'
            )
            self.zoom_ax.add_patch(rect)
            self.preview_patches.append(rect)
            self.canvas.draw_idle()

    def _clear_preview_patches(self):
        for p in self.preview_patches:
            try: p.remove()
            except Exception: pass
        self.preview_patches.clear()

    def on_release(self, event):
        if self._disposed:
            return
        self._clear_preview_patches()

        if self.mode == "CURSOR":
            self.dragging_cursor = None
            if self.on_cursor_change:
                self.on_cursor_change()

        elif self.mode == "HAND":
            self.panning = False
            self.pan_start_display_x = None
            self.pan_start_display_y = None
            self.pan_target_ax = None

        elif self.mode in ["ZOOM_X", "ZOOM_Y", "ZOOM_XY"]:
            release_x = self._event_time(event)
            if self.mode in ["ZOOM_X", "ZOOM_XY"] and self.zoom_start_x is not None and release_x is not None:
                x0, x1 = sorted([self.zoom_start_x, release_x])
                if abs(x1 - x0) > 0.001:
                    self._set_time_xlim((x0, x1))

            release_y = None
            if self.zoom_ax is not None and event.x is not None and event.y is not None:
                try:
                    release_y = self.zoom_ax.transData.inverted().transform((event.x, event.y))[1]
                except Exception:
                    release_y = event.ydata
            elif event.inaxes is self.zoom_ax:
                release_y = event.ydata

            if self.mode in ["ZOOM_Y", "ZOOM_XY"] and self.zoom_start_y is not None and release_y is not None and self.zoom_ax is not None:
                y0, y1 = sorted([self.zoom_start_y, release_y])
                if abs(y1 - y0) > 0.001:
                    self.zoom_ax.set_ylim(y0, y1)

            self.zoom_start_x = None
            self.zoom_start_y = None
            self.zoom_ax = None
            self.canvas.draw_idle()

        current_view = self._get_current_view()
        if self._pending_view and views_differ(self._pending_view, current_view):
            self._push_view(self.history_views, self._pending_view)
            self.forward_views.clear()
        self._pending_view = None

    def on_scroll(self, event):
        if (self._disposed or event.inaxes not in self.axes + self.twin_axes
                or self._is_event_on_legend(event)):
            return

        modifiers = set(str(getattr(event, 'key', '') or '').lower().split('+'))
        if 'alt' in modifiers:
            # Alt is owned by the host's block-scroll gesture.
            return
        if event.button not in ('up', 'down'):
            return

        current_view = self._get_current_view()

        base_scale = 1.25
        scale_factor = 1.0 / base_scale if event.button == 'up' else base_scale

        if 'shift' in modifiers and event.ydata is not None:
            cur_ylim = event.inaxes.get_ylim()
            ydata = event.ydata
            if np.isfinite(ydata) and cur_ylim[1] != cur_ylim[0]:
                new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
                rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])
                event.inaxes.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        elif 'shift' not in modifiers and event.xdata is not None and np.isfinite(event.xdata):
            cur_xlim = self.axes[0].get_xlim()
            if cur_xlim[1] != cur_xlim[0]:
                xdata = event.xdata
                new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
                relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
                new_xlim = [xdata - new_width * (1 - relx), xdata + new_width * relx]
                self._set_time_xlim(new_xlim)

        if views_differ(current_view, self._get_current_view()):
            if not self.history_views or views_differ(self.history_views[-1], current_view):
                self._push_view(self.history_views, current_view)
            self.forward_views.clear()
        self.canvas.draw_idle()

    def _show_context_menu(self, event):
        get_widget = getattr(self.canvas, 'get_tk_widget', None)
        if not callable(get_widget):
            return
        if self._context_menu is not None:
            self._context_menu.destroy()
        menu = tk.Menu(get_widget(), tearoff=0)
        self._context_menu = menu

        x_click = event.xdata
        if x_click is not None:
            menu.add_command(
                label=f"🔴 Move C1 (Red) Here ({x_click:.2f} min)",
                command=lambda: self._set_c1_time(x_click)
            )
            menu.add_command(
                label=f"🔵 Move C2 (Blue) Here ({x_click:.2f} min)",
                command=lambda: self._set_c2_time_and_activate(x_click)
            )
            menu.add_separator()

        menu.add_command(label="📏 Toggle Dual Cursor (Δt)", command=self.toggle_dual_cursor)
        menu.add_command(label="◀ Zoom Back (Previous View) [Backspace]", command=self.zoom_back)
        menu.add_command(label="▶ Zoom Forward [Alt+Right]", command=self.zoom_forward)
        menu.add_command(label="🔄 Reset Zoom (Fit All)", command=self.reset_zoom)
        menu.add_separator()

        tools_menu = tk.Menu(menu, tearoff=0)
        tools_menu.add_command(label="📍 Cursor Mode", command=lambda: self.set_mode("CURSOR"))
        tools_menu.add_command(label="✋ Hand Pan Tool (2D)", command=lambda: self.set_mode("HAND"))
        tools_menu.add_command(label="🔍 Zoom X (Horizontal)", command=lambda: self.set_mode("ZOOM_X"))
        tools_menu.add_command(label="🔍 Zoom Y (Vertical)", command=lambda: self.set_mode("ZOOM_Y"))
        tools_menu.add_command(label="🔎 Zoom XY (2D Box)", command=lambda: self.set_mode("ZOOM_XY"))
        menu.add_cascade(label="🛠 Interaction Tools", menu=tools_menu)
        menu.add_separator()

        if self.on_export_excel:
            menu.add_command(label="📊 Save Excel Workbook (.xlsx)", command=self.on_export_excel)
        if self.on_export_image:
            menu.add_command(label="💾 Save Graph Image (PNG/PDF)", command=self.on_export_image)
        if self.on_export_csv:
            menu.add_command(label="📋 Save Synchronized CSV", command=self.on_export_csv)

        try:
            if hasattr(event, 'guiEvent') and event.guiEvent:
                menu.tk_popup(event.guiEvent.x_root, event.guiEvent.y_root)
            else:
                widget = self.canvas.get_tk_widget()
                menu.tk_popup(
                    widget.winfo_rootx() + int(event.x),
                    widget.winfo_rooty() + widget.winfo_height() - int(event.y)
                )
        finally:
            menu.grab_release()
