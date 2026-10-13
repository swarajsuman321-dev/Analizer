"""Vector state symbols for signal scales, independent of installed fonts."""

from matplotlib.offsetbox import AnnotationBbox, DrawingArea
from matplotlib.patches import Circle, FancyBboxPatch, PathPatch
from matplotlib.path import Path


def _padlock_drawing(locked, color):
    """Draw a 14 by 18 point padlock; an open shackle has a visible gap."""
    drawing = DrawingArea(14, 18, clip=False)
    if locked:
        vertices = [
            (3.5, 10.0), (3.5, 13.0),
            (3.5, 16.5), (7.0, 16.5),
            (10.5, 16.5), (10.5, 13.0), (10.5, 10.0),
        ]
    else:
        # The left stem stays attached while the right stem ends well above
        # the body, making the unlocked state visible at small sizes.
        vertices = [
            (3.5, 10.0), (3.5, 14.0),
            (3.5, 17.0), (7.0, 17.0),
            (10.5, 17.0), (10.5, 14.0), (10.5, 12.5),
        ]
    shackle = PathPatch(
        Path(vertices, [
            Path.MOVETO, Path.LINETO,
            Path.CURVE3, Path.CURVE3,
            Path.CURVE3, Path.CURVE3, Path.LINETO,
        ]),
        facecolor='none', edgecolor=color, linewidth=1.4,
        capstyle='round', joinstyle='round', clip_on=False,
    )
    body = FancyBboxPatch(
        (2, 1), 10, 9, boxstyle='round,pad=0,rounding_size=1.1',
        facecolor='white', edgecolor=color, linewidth=1.1,
        clip_on=False,
    )
    drawing.add_artist(shackle)
    drawing.add_artist(body)
    drawing.add_artist(Circle(
        (7, 6.4), radius=0.9, facecolor=color, edgecolor='none',
        clip_on=False,
    ))
    drawing.add_artist(PathPatch(
        Path(
            [(6.65, 5.8), (6.4, 3.5), (7.6, 3.5), (7.35, 5.8), (6.65, 5.8)],
            [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY],
        ),
        facecolor=color, edgecolor='none', clip_on=False,
    ))
    return drawing


def attach_lock_state_icons(axis, side, color):
    """Place open and closed padlocks at the 0 and 1 ticks of a state axis.

    The annotation dimensions and offsets are physical points, so the icons
    retain their proportions when the chart is resized or exported. Layout
    code may refresh each annotation's ``xycoords`` after moving its spine.
    """
    if side not in ('left', 'right'):
        raise ValueError("Lock symbols require a 'left' or 'right' axis side.")
    existing = list(getattr(axis, '_signal_state_icons', []))
    retained = []
    for entry in existing:
        if entry['side'] == side:
            entry['artist'].remove()
        else:
            retained.append(entry)

    transform = axis.get_yaxis_transform('tick1' if side == 'left' else 'tick2')
    x_position = 0 if side == 'left' else 1
    x_offset = -11 if side == 'left' else 11
    entries = []
    for value in (0, 1):
        annotation = AnnotationBbox(
            _padlock_drawing(locked=bool(value), color=color),
            (x_position, value), xycoords=transform,
            xybox=(x_offset, 0), boxcoords='offset points',
            box_alignment=(0.5, 0.5), frameon=False, pad=0,
            annotation_clip=False,
        )
        annotation.set_clip_on(False)
        annotation.set_zorder(5)
        annotation.set_in_layout(False)
        axis.add_artist(annotation)
        entries.append({'value': value, 'side': side, 'artist': annotation})
    axis._signal_state_icons = retained + entries
    return entries
