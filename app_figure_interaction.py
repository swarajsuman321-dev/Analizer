"""Matplotlib legend interaction shared by comparison renderers."""
from matplotlib.backend_bases import PickEvent


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


