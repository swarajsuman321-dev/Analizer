import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

def build_refined_clean_logo():
    output_dir = os.path.dirname(os.path.abspath(__file__))
    # 2048x2048 master resolution for supersampling
    size = 2048
    pad = 112
    r = 440

    # 1. Base Gradient Canvas (Deep Industrial Navy to Slate Cobalt)
    bg = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)

    for y in range(size):
        t = y / size
        cr = int(5 + 18 * t)
        cg = int(14 + 48 * t)
        cb = int(32 + 88 * t)
        bg_draw.line([(0, y), (size, y)], fill=(cr, cg, cb, 255))

    # 2. Mask for the rounded squircle badge
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=r, fill=255)

    final_badge = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    final_badge.paste(bg, (0, 0), mask=mask)

    # 3. Oscilloscope Grid Layer
    grid_overlay = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid_overlay)

    center_x, center_y = size // 2, size // 2
    grid_color = (0, 229, 255, 34)
    grid_axis_color = (0, 229, 255, 75)

    step = 180
    for x in range(pad + 120, size - pad, step):
        grid_draw.line([(x, pad + 60), (x, size - pad - 60)], fill=grid_color, width=3)
    for y in range(pad + 120, size - pad, step):
        grid_draw.line([(pad + 60, y), (size - pad - 60, y)], fill=grid_color, width=3)

    # Center crosshairs & ticks
    grid_draw.line([(center_x, pad + 50), (center_x, size - pad - 50)], fill=grid_axis_color, width=5)
    grid_draw.line([(pad + 50, center_y), (size - pad - 50, center_y)], fill=grid_axis_color, width=5)

    for y in range(pad + 80, size - pad - 80, step // 2):
        grid_draw.line([(center_x - 12, y), (center_x + 12, y)], fill=grid_axis_color, width=3)
    for x in range(pad + 80, size - pad - 80, step // 2):
        grid_draw.line([(x, center_y - 12), (x, center_y + 12)], fill=grid_axis_color, width=3)

    final_badge = Image.alpha_composite(final_badge, grid_overlay)

    # 4. Appliance Drum & Rotor Reticle
    drum_overlay = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    drum_draw = ImageDraw.Draw(drum_overlay)

    drum_r = 600
    drum_draw.ellipse([center_x - drum_r, center_y - drum_r, center_x + drum_r, center_y + drum_r], 
                      outline=(255, 255, 255, 45), width=7)
    drum_draw.ellipse([center_x - drum_r + 40, center_y - drum_r + 40, center_x + drum_r - 40, center_y + drum_r - 40], 
                      outline=(0, 229, 255, 50), width=4)

    num_dots = 16
    for i in range(num_dots):
        ang = 2 * math.pi * i / num_dots
        dx = center_x + (drum_r - 80) * math.cos(ang)
        dy = center_y + (drum_r - 80) * math.sin(ang)
        drum_draw.ellipse([dx - 11, dy - 11, dx + 11, dy + 11], fill=(0, 229, 255, 140))

    final_badge = Image.alpha_composite(final_badge, drum_overlay)

    # 5. Dynamic Test Waveforms
    x_start = pad + 100
    x_end = size - pad - 100
    xs = np.linspace(x_start, x_end, 600)

    points = []
    for x in xs:
        norm_x = (x - x_start) / (x_end - x_start)
        if norm_x < 0.2:
            y = center_y + 240
        elif norm_x < 0.32:
            prog = (norm_x - 0.2) / 0.12
            surge = math.sin(prog * math.pi * 0.5)
            y = (center_y + 240) - surge * 600
        elif norm_x < 0.58:
            wave_comp = math.sin((norm_x - 0.32) * 45) * 56
            y = (center_y - 360) + wave_comp
        elif norm_x < 0.72:
            prog = (norm_x - 0.58) / 0.14
            y = (center_y - 360) + prog * 440
        else:
            y = center_y + 80 + math.sin((norm_x - 0.72) * 20) * 32
        points.append((x, y))

    # Glow layer for cyan active power wave
    glow_overlay = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_overlay)
    glow_draw.line(points, fill=(0, 229, 255, 160), width=36)
    glow_overlay = glow_overlay.filter(ImageFilter.GaussianBlur(radius=18))
    final_badge = Image.alpha_composite(final_badge, glow_overlay)

    # Waveforms & Calipers
    wave_overlay = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    wave_draw = ImageDraw.Draw(wave_overlay)

    # Golden Amber Energy Curve (Wh)
    ramp_points = []
    for x in xs:
        norm_x = (x - x_start) / (x_end - x_start)
        s_val = 1 / (1 + math.exp(-10 * (norm_x - 0.45)))
        y = (center_y + 340) - s_val * 460
        ramp_points.append((x, y))

    for i in range(len(ramp_points) - 1):
        if (i // 6) % 2 == 0:
            wave_draw.line([ramp_points[i], ramp_points[i+1]], fill=(255, 171, 0, 245), width=9)

    # Cyan Active Power Wave with White Core
    wave_draw.line(points, fill=(0, 229, 255, 230), width=13)
    wave_draw.line(points, fill=(255, 255, 255, 255), width=6)

    # Dual Caliper Cursors (C1 Red, C2 Blue)
    c1_x = int(x_start + (x_end - x_start) * 0.32)
    c2_x = int(x_start + (x_end - x_start) * 0.70)

    # C1 Line
    for y in range(pad + 120, size - pad - 120, 44):
        wave_draw.line([(c1_x, y), (c1_x, y + 24)], fill=(255, 59, 48, 240), width=6)

    # C2 Line
    for y in range(pad + 120, size - pad - 120, 44):
        wave_draw.line([(c2_x, y), (c2_x, y + 24)], fill=(10, 132, 255, 240), width=6)

    # Caliper Delta Indicator Bar (Spring Green)
    y_delta = pad + 180
    wave_draw.line([(c1_x, y_delta), (c2_x, y_delta)], fill=(0, 230, 118, 245), width=6)
    wave_draw.line([(c1_x, y_delta - 22), (c1_x, y_delta + 22)], fill=(0, 230, 118, 245), width=6)
    wave_draw.line([(c2_x, y_delta - 22), (c2_x, y_delta + 22)], fill=(0, 230, 118, 245), width=6)

    # Intersection Beads
    pt_c1 = points[int(len(points) * 0.32)]
    wave_draw.ellipse([pt_c1[0] - 20, pt_c1[1] - 20, pt_c1[0] + 20, pt_c1[1] + 20], 
                      fill=(255, 59, 48, 255), outline=(255, 255, 255, 255), width=6)

    pt_c2 = points[int(len(points) * 0.70)]
    wave_draw.ellipse([pt_c2[0] - 20, pt_c2[1] - 20, pt_c2[0] + 20, pt_c2[1] + 20], 
                      fill=(10, 132, 255, 255), outline=(255, 255, 255, 255), width=6)

    final_badge = Image.alpha_composite(final_badge, wave_overlay)

    # 6. Clean Outer Perimeter Rim Only (No cutting arcs)
    border_overlay = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_overlay)
    border_draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=r, outline=(255, 255, 255, 60), width=8)
    border_draw.rounded_rectangle([pad + 4, pad + 4, size - pad - 4, size - pad - 4], radius=r - 4, outline=(0, 229, 255, 45), width=3)
    final_badge = Image.alpha_composite(final_badge, border_overlay)

    # Clip strictly inside the squircle
    badge_clipped = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    badge_clipped.paste(final_badge, (0, 0), mask=mask)

    # 7. Soft Natural Drop Shadow
    shadow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([pad, pad + 35, size - pad, size - pad + 35], radius=r, fill=(0, 0, 0, 130))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=38))

    final_master = Image.alpha_composite(shadow, badge_clipped)

    # 8. Export 1024x1024 PNG and multi-resolution Windows ICO
    final_1024 = final_master.resize((1024, 1024), Image.Resampling.LANCZOS)
    final_1024.save(os.path.join(output_dir, 'app_logo.png'))

    ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    final_1024.save(os.path.join(output_dir, 'app_icon.ico'), format='ICO', sizes=ico_sizes)
    print("Clean icon generated as 'app_icon.ico' and 'app_logo.png'.")

if __name__ == "__main__":
    build_refined_clean_logo()
