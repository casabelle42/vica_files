import tkinter as tk
from typing import Optional
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageOps, ImageFont, ImageChops
from dataclasses import dataclass
import os
import sys
from tkinter import messagebox

# Add project root to path for imports
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@dataclass
class SplashConfig:
    enabled: bool = True
    start_delay_ms: int = 900
    duration_ms: int = 1200
    steps: int = 30
    logo_opacity: float = 0.9
    logo_max_width_ratio: float = 0.55
    logo_max_height_ratio: float = 0.55


def create_signin_window(config: Optional[SplashConfig] = None) -> tk.Tk:
    root = tk.Tk()
    root.title("Sign In")

    # Dimensions
    root.geometry("1400x1024")

    # Appearance
    root.attributes("-alpha", 1.0)  # 100% opacity
    root.configure(bg="#1D2BA1")  # Fill color

    # Step 1: State - StringVars for username and password
    root.username_var = tk.StringVar(value="")
    root.password_var = tk.StringVar(value="")

    # Resolve logo path relative to this file: ./assets/logo.png
    assets_dir = Path(__file__).parent / "assets"
    logo_path = assets_dir / "logo.png"

    # Centered logo
    add_center_logo(root, image_path=str(logo_path))

    # Glass overlay panel on top (shows blurred, faint logo through)
    add_glass_panel(
        root,
        width=793,
        height=869,
        corner_radius=75,
        opacity=0.8,
        background_logo_path=str(logo_path),
        background_color="#1D2BA1",
        titles=[
            {"text": "Username", "y_offset": 90},
            {"text": "Password", "y_offset": 340},
        ],
        inputs=[
            {"placeholder": "Enter username", "y_offset": 235},
            {"placeholder": "Enter password", "y_offset": 485},
        ],
        buttons=[{"text": "Sign in"}],
    )

    # Step 2: Place real Entry widgets over the pill visuals
    add_interactive_entries(root)

    # Step 2-4: Splash overlay (configurable)
    cfg = config or SplashConfig()
    # Env override to quickly disable splash: set SIGNIN_DISABLE_SPLASH=1
    if os.getenv("SIGNIN_DISABLE_SPLASH", "0") == "1":
        cfg.enabled = False
    # Auto-disable if logo asset missing
    if not logo_path.exists():
        cfg.enabled = False
    if cfg.enabled:
        root._splash = create_splash_overlay(root, width=1400, height=1024, bg="#1D2BA1")
        # Step 3: After overlay is positioned and sized, place the logo on it
        # Match overlay logo size to the faint logo inside the glass panel:
        # panel size (793x869) with 0.92 contain factor → target max (729 x 799)
        match_panel_w, match_panel_h = 793, 869
        target_w = int(match_panel_w * 0.92)  # 729
        target_h = int(match_panel_h * 0.92)  # 799
        ratio_w = target_w / 1400.0
        ratio_h = target_h / 1024.0
        root.after(
            80,
            lambda: set_overlay_logo(
                root._splash,
                image_path=str(logo_path),
                opacity=cfg.logo_opacity,
                max_width_ratio=ratio_w,
                max_height_ratio=ratio_h,
            ),
        )
        # Step 4 new sequence using single splash window:
        # 1) Keep splash alpha at 1.0 and fade the logo image itself to blue.
        # 2) After logo is gone, fade the whole splash window away to reveal the panel.
        root.after(
            cfg.start_delay_ms,
            lambda: fade_logo_then_window(root._splash, logo_duration_ms=700, logo_steps=24, window_duration_ms=700, window_steps=30),
        )

    return root


def add_center_logo(root: tk.Tk, image_path: str, width: int = 782, height: int = 776) -> Optional[tk.Widget]:
    """
    Adds a centered logo with 20% opacity on a D9D9D9 background.
    Returns the created container or None if image not found.
    """
    container = tk.Frame(root, width=width, height=height, bg="#D9D9D9", bd=0, highlightthickness=0)
    container.place(relx=0.5, rely=0.5, anchor="center")

    try:
        img = Image.open(image_path).convert("RGBA").resize((width, height), Image.LANCZOS)
        # Reduce image opacity to 20%
        r, g, b, a = img.split()
        a = a.point(lambda p: int(p * 0.3))  # make logo pop a bit more
        img.putalpha(a)

        photo = ImageTk.PhotoImage(img)
        label = tk.Label(container, image=photo, bg="#D9D9D9", bd=0, highlightthickness=0)
        label.image = photo  # keep reference
        label.place(relx=0.5, rely=0.5, anchor="center")
        return container
    except FileNotFoundError:
        # Simple fallback indicator so the layout is still visible
        placeholder = tk.Label(
            container,
            text="Place logo at: {}".format(image_path),
            bg="#D9D9D9",
            fg="#333333",
        )
        placeholder.place(relx=0.5, rely=0.5, anchor="center")
        return None


def add_glass_panel(
    root: tk.Tk,
    width: int = 793,
    height: int = 869,
    corner_radius: int = 75,
    opacity: float = 0.8,
    background_logo_path: Optional[str] = None,
    background_color: str = "#1D2BA1",
    stroke_enabled: bool = False,
    titles=None,
    inputs=None,
    buttons=None,
) -> tk.Widget:
    """
    Adds a centered rounded-rectangle 'glass' panel with a vertical linear gradient
    and a blurred, faint background logo to simulate transparency.
    start #131A5C (top, 0%) → end #B8DDFF (bottom, 100%), overall tint opacity at 80%.
    """
    # Helper: hex -> (r,g,b)
    def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
        h = hex_str.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

    # Base canvas to simulate what's behind the glass (root background color)
    base = Image.new("RGBA", (width, height), (*hex_to_rgb(background_color), 255))

    # Optionally place a faint, blurred logo on the base to emulate look-through
    if background_logo_path:
        try:
            logo = Image.open(background_logo_path).convert("RGBA")
            # Fit logo within the panel while keeping aspect ratio
            max_logo_w, max_logo_h = int(width * 0.92), int(height * 0.92)
            logo_fit = ImageOps.contain(logo, (max_logo_w, max_logo_h), Image.LANCZOS)
            # Center position
            lx = (width - logo_fit.width) // 2
            ly = (height - logo_fit.height) // 2
            # Reduce logo opacity to 20% and blur slightly to mimic frosted diffusion
            r, g, b, a = logo_fit.split()
            a = a.point(lambda p: int(p * 0.30))  # increase visibility slightly
            logo_fit.putalpha(a)
            logo_blurred = logo_fit.filter(ImageFilter.GaussianBlur(radius=3))  # slightly crisper
            base.alpha_composite(logo_blurred, (lx, ly))
        except FileNotFoundError:
            pass

    # Optional: inside stroke UNDER the glass tint/shadows (equivalent to Figma "stroke on/off")
    if stroke_enabled:
        stroke_weight = 10
        stroke_rgb = hex_to_rgb("#D9D9D9")
        stroke_layer_under = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        stroke_draw_under = ImageDraw.Draw(stroke_layer_under)
        inset_under = stroke_weight // 2
        stroke_radius_under = max(corner_radius - inset_under, 0)
        stroke_box_under = (inset_under, inset_under, width - 1 - inset_under, height - 1 - inset_under)
        stroke_draw_under.rounded_rectangle(
            stroke_box_under,
            radius=stroke_radius_under,
            outline=(*stroke_rgb, 255),
            width=stroke_weight,
        )
        base.alpha_composite(stroke_layer_under)

    # Build vertical gradient (RGB) to tint the glass
    start_rgb = (0x13, 0x1A, 0x5C)
    end_rgb = (0xB8, 0xDD, 0xFF)
    gradient_rgb = Image.new("RGB", (width, height), start_rgb)
    draw = ImageDraw.Draw(gradient_rgb)
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
        g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
        b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Create rounded alpha mask with desired opacity for the tint layer
    alpha_value = int(max(0.0, min(1.0, opacity)) * 255)
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [(0, 0), (width, height)],
        radius=corner_radius,
        fill=alpha_value,
    )

    gradient = gradient_rgb.convert("RGBA")
    gradient.putalpha(mask)

    # Compose: base (faint logo) under gradient tint
    composed = Image.alpha_composite(base, gradient)

    # Inner shadow: color #5C69D4, blur 15, spread 8 (inside)
    inner_shadow_color = (0x5C, 0x69, 0xD4, 255)
    blur_radius = 15
    spread = 8
    ring = Image.new("L", (width, height), 0)
    ring_draw = ImageDraw.Draw(ring)
    # Outer rounded rect (edge)
    ring_draw.rounded_rectangle([(0, 0), (width - 1, height - 1)], radius=corner_radius, fill=255)
    # Cut inner area to keep only an inside ring of thickness ~spread
    inner_box = (spread, spread, width - 1 - spread, height - 1 - spread)
    ring_draw.rounded_rectangle(inner_box, radius=max(corner_radius - spread, 0), fill=0)
    ring = ring.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    shadow_layer = Image.new("RGBA", (width, height), inner_shadow_color)
    shadow_layer.putalpha(ring)
    composed = Image.alpha_composite(composed, shadow_layer)

    # Render optional input boxes onto the glass
    if inputs:
        pill_w, pill_h = 696, 90
        pill_radius = 45
        # Colors from spec
        stroke_rgb = (0x1D, 0x2B, 0xA1)  # #1D2BA1
        top_rgb = (0x9C, 0xA2, 0xBC)     # #9CA2BC
        bottom_rgb = (0xFF, 0xFF, 0xFF)  # #FFFFFF

        # Font for placeholder
        fonts_dir = Path(__file__).parent / "assets" / "fonts"
        duru_path = fonts_dir / "DuruSans-Regular.ttf"
        if duru_path.exists():
            placeholder_font = ImageFont.truetype(str(duru_path), 28)
        else:
            placeholder_font = ImageFont.truetype("segoeui.ttf", 28) if Path("C:/Windows/Fonts/segoeui.ttf").exists() else ImageFont.load_default()

        # Keep track of pill hitboxes for interactivity
        pill_bboxes = {}

        for spec in inputs:
            placeholder = spec.get("placeholder", "Enter username")
            y_offset = int(spec.get("y_offset", 170))

            # Canvas for the pill (outer drop shadow drawn directly onto panel)
            pad = 0
            pill_img = Image.new("RGBA", (pill_w, pill_h), (0, 0, 0, 0))

            # Base rounded rectangle mask (full pill)
            mask = Image.new("L", (pill_w, pill_h), 0)
            md = ImageDraw.Draw(mask)
            md.rounded_rectangle([(0, 0), (pill_w - 1, pill_h - 1)], radius=pill_radius, fill=255)

            # Compute placement on panel (centered horizontally)
            px = (width - pill_w) // 2
            py = y_offset

            # No outer drop shadow: ensure pill does not affect the glass panel background

            # Solid fill inside: 9CA2BC @ 100%
            fill = Image.new("RGBA", (pill_w, pill_h), (*top_rgb, 255))
            fill.putalpha(mask)
            pill_img.alpha_composite(fill, (0, 0))

            # Inset/caved-in effect entirely INSIDE the stroke region
            stroke_w = 4
            bevel = 8
            outer_inset = max(stroke_w - 2, 0)
            # Outer mask for bevel ring (never touches stroke)
            outer = Image.new("L", (pill_w, pill_h), 0)
            ImageDraw.Draw(outer).rounded_rectangle(
                [(outer_inset, outer_inset), (pill_w - 1 - outer_inset, pill_h - 1 - outer_inset)],
                radius=pill_radius - outer_inset,
                fill=255,
            )
            # Inner mask for bevel ring
            inner_inset = outer_inset + bevel
            inner = Image.new("L", (pill_w, pill_h), 0)
            ImageDraw.Draw(inner).rounded_rectangle(
                [(inner_inset, inner_inset), (pill_w - 1 - inner_inset, pill_h - 1 - inner_inset)],
                radius=max(pill_radius - inner_inset, 0),
                fill=255,
            )
            ring_mask = ImageChops.subtract(outer, inner).filter(ImageFilter.GaussianBlur(radius=2))

            # Emphasize the top part of the ring for the caved shadow
            top_grad = Image.new("L", (pill_w, pill_h), 0)
            tg = ImageDraw.Draw(top_grad)
            for y in range(pill_h):
                t = y / max(pill_h - 1, 1)
                val = int(255 * max(0.0, 1.6 - 2.6 * t))  # stronger at top, fades quicker by mid
                tg.line([(0, y), (pill_w, y)], fill=val)
            dark_mask = ImageChops.multiply(ring_mask, top_grad)
            # Boost shadow intensity to bring the cave effect back
            # Intensify shadow 3 additional times at x1.8 each (capped)
            for _ in range(3):
                dark_mask = dark_mask.point(lambda p: min(255, int(p * 1.8)))
            dark_layer = Image.new("RGBA", (pill_w, pill_h), (0x0C, 0x22, 0x72, 255))  # deeper cool blue
            dark_layer.putalpha(dark_mask)
            pill_img.alpha_composite(dark_layer, (0, 0))

            # Subtle inner light rim near bottom to complete the bevel
            bottom_grad = Image.new("L", (pill_w, pill_h), 0)
            bgd = ImageDraw.Draw(bottom_grad)
            for y in range(pill_h):
                t = y / max(pill_h - 1, 1)
                val = int(255 * max(0.0, (t - 0.60) * 3.0))  # starts lower, stronger near bottom
                bgd.line([(0, y), (pill_w, y)], fill=val)
            light_mask = ImageChops.multiply(ring_mask, bottom_grad)
            light_layer = Image.new("RGBA", (pill_w, pill_h), (255, 255, 255, 120))
            light_layer.putalpha(light_mask)
            pill_img.alpha_composite(light_layer, (0, 0))

            # Gentle dark edge shadow around entire inner perimeter to avoid "white rim"
            edge_shadow = Image.new("RGBA", (pill_w, pill_h), (10, 20, 70, 70))  # cool dark tone, low alpha
            edge_shadow.putalpha(ring_mask)
            pill_img.alpha_composite(edge_shadow, (0, 0))

            # Inner white highlight just inside stroke (kept away from edge)
            highlight = Image.new("RGBA", (pill_w, pill_h), (255, 255, 255, 0))
            hd = ImageDraw.Draw(highlight)
            inset = stroke_w + 3
            hd.rounded_rectangle(
                [(inset, inset), (pill_w - 1 - inset, pill_h - 1 - inset)],
                radius=pill_radius - inset,
                outline=(255, 255, 255, 40),
                width=1,
            )
            pill_img.alpha_composite(highlight, (0, 0))

            # Edge smoothing: slightly blur the alpha channel to remove rough/jagged edges
            alpha_smoothed = pill_img.split()[-1].filter(ImageFilter.GaussianBlur(radius=0.8))
            pill_img.putalpha(alpha_smoothed)

            # Stroke (crisp)
            stroke_layer = Image.new("RGBA", (pill_w, pill_h), (0, 0, 0, 0))
            sd = ImageDraw.Draw(stroke_layer)
            sd.rounded_rectangle(
                [(0, 0), (pill_w - 1, pill_h - 1)],
                radius=pill_radius,
                outline=(*stroke_rgb, 255),
                width=4,
            )
            pill_img.alpha_composite(stroke_layer, (0, 0))

            # Placeholder text
            text_mask = Image.new("L", (pill_w, pill_h), 0)
            tdraw = ImageDraw.Draw(text_mask)
            bbox = tdraw.textbbox((0, 0), placeholder, font=placeholder_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx, ty = (pill_w - tw) // 2, (pill_h - th) // 2 - 2
            tdraw.text((tx, ty), placeholder, fill=255, font=placeholder_font)
            text_rgba = Image.new("RGBA", (pill_w, pill_h), (255, 255, 255, 235))
            text_rgba.putalpha(text_mask)
            pill_img.alpha_composite(text_rgba, (0, 0))

            # Paste pill onto panel
            composed.alpha_composite(pill_img, (px, py))

            # Record bbox for click-to-focus later
            key = "username" if "user" in placeholder.lower() else ("password" if "pass" in placeholder.lower() else None)
            if key:
                pill_bboxes[key] = (px, py, px + pill_w, py + pill_h)

    # Render optional titles directly onto the glass so they "belong" to the panel
    if titles:
        # Prepare font (Duru Sans preferred)
        fonts_dir = Path(__file__).parent / "assets" / "fonts"
        duru_path = fonts_dir / "DuruSans-Regular.ttf"
        if duru_path.exists():
            font = ImageFont.truetype(str(duru_path), 64)
        else:
            font = ImageFont.truetype("segoeui.ttf", 64) if Path("C:/Windows/Fonts/segoeui.ttf").exists() else ImageFont.load_default()

        title_w, title_h = 404, 84
        shadow_blur = 25
        pad = shadow_blur * 2  # padding so blurred shadow isn't clipped
        for spec in titles:
            text = spec.get("text", "")
            y_offset = int(spec.get("y_offset", 90))

            # Build text mask centered
            text_mask = Image.new("L", (title_w + 2 * pad, title_h + 2 * pad), 0)
            dm = ImageDraw.Draw(text_mask)
            bbox = dm.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = pad + (title_w - tw) // 2
            ty = pad + (title_h - th) // 2
            dm.text((tx, ty), text, fill=255, font=font)

            # Gradient fill for text
            start_rgb = (0xFF, 0xFF, 0xFF)
            end_rgb = (0xFF, 0xF3, 0xDD)
            text_rgba = Image.new("RGBA", (title_w + 2 * pad, title_h + 2 * pad), (0, 0, 0, 0))
            td = ImageDraw.Draw(text_rgba)
            for y in range(title_h + 2 * pad):
                t = min(max((y - pad) / max(title_h - 1, 1), 0.0), 1.0)
                r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
                g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
                b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
                td.line([(0, y), (title_w + 2 * pad, y)], fill=(r, g, b, 255))
            text_rgba.putalpha(text_mask.point(lambda p: int(p * 0.90)))

            # Drop shadow under text
            shadow = Image.new("RGBA", (title_w + 2 * pad, title_h + 2 * pad), (0, 0, 0, 0))
            shadow_mask = text_mask.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
            shadow.putalpha(shadow_mask)

            text_composed = Image.alpha_composite(shadow, text_rgba)

            # Paste centered horizontally on the panel at y_offset
            px = (width - title_w) // 2 - pad
            py = y_offset - pad
            composed.alpha_composite(text_composed, (px, py))

    # Render optional buttons (e.g., "Sign in") on the glass
    if buttons:
        # Preferred font
        fonts_dir = Path(__file__).parent / "assets" / "fonts"
        duru_path = fonts_dir / "DuruSans-Regular.ttf"
        if duru_path.exists():
            btn_font = ImageFont.truetype(str(duru_path), 48)
        else:
            btn_font = ImageFont.truetype("segoeui.ttf", 48) if Path("C:/Windows/Fonts/segoeui.ttf").exists() else ImageFont.load_default()

        btn_w, btn_h = 339, 101
        btn_radius = 50
        btn_fill_rgb = (0x05, 0x11, 0x40)  # #051140
        txt_top = (0xFF, 0xF3, 0xDD)       # #FFF3DD
        txt_bottom = (0xFF, 0xFF, 0xFF)    # #FFFFFF

        # Prepare hover/pressed composites
        composed_hover = composed.copy()
        composed_pressed = composed.copy()
        button_bbox = None

        for spec in buttons:
            label = spec.get("text", "Sign in")
            y_offset = int(spec.get("y_offset", height - btn_h - 70))

            btn = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
            mask = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [(0, 0), (btn_w - 1, btn_h - 1)], radius=btn_radius, fill=255
            )

            # Solid fill
            base_btn = Image.new("RGBA", (btn_w, btn_h), (*btn_fill_rgb, 255))
            base_btn.putalpha(mask)
            btn.alpha_composite(base_btn, (0, 0))

            # Restore original highlight: inner top highlight + glossy top band
            # Inner top highlight
            hi = Image.new("RGBA", (btn_w, btn_h), (255, 255, 255, 0))
            grad = Image.new("L", (btn_w, btn_h), 0)
            gd = ImageDraw.Draw(grad)
            cutoff = int(btn_h * 0.45)
            for y in range(cutoff):
                a = int(90 * (1.0 - y / max(cutoff - 1, 1)))
                gd.line([(0, y), (btn_w, y)], fill=a)
            inset_hi = 6
            clip_hi = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(clip_hi).rounded_rectangle(
                [(inset_hi, inset_hi), (btn_w - 1 - inset_hi, btn_h - 1 - inset_hi)],
                radius=btn_radius - inset_hi,
                fill=255,
            )
            grad = ImageChops.multiply(grad, clip_hi).filter(ImageFilter.GaussianBlur(radius=2))
            hi.putalpha(grad)
            btn.alpha_composite(hi, (0, 0))

            # Glossy top band
            sheen = Image.new("RGBA", (btn_w, btn_h), (255, 255, 255, 0))
            sheen_grad = Image.new("L", (btn_w, btn_h), 0)
            sgd = ImageDraw.Draw(sheen_grad)
            sheen_h = int(btn_h * 0.38)
            max_a = 60
            for y in range(sheen_h):
                a = int(max_a * (1.0 - y / max(sheen_h - 1, 1)))
                sgd.line([(0, y), (btn_w, y)], fill=a)
            clip_mask = Image.new("L", (btn_w, btn_h), 0)
            inset = 8
            ImageDraw.Draw(clip_mask).rounded_rectangle(
                [(inset, inset), (btn_w - 1 - inset, btn_h - 1 - inset)],
                radius=btn_radius - inset,
                fill=255,
            )
            sheen_mask = ImageChops.multiply(sheen_grad, clip_mask).filter(ImageFilter.GaussianBlur(radius=2))
            sheen.putalpha(sheen_mask)
            btn.alpha_composite(sheen, (0, 0))

            # Step 4: refined inner ring (2px) for modern glass edge
            rim_outer_inset = 7
            rim_thickness = 2
            rim_inner_inset = rim_outer_inset + rim_thickness
            # Build ring mask inside button
            outer_rim = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(outer_rim).rounded_rectangle(
                [(rim_outer_inset, rim_outer_inset), (btn_w - 1 - rim_outer_inset, btn_h - 1 - rim_outer_inset)],
                radius=btn_radius - rim_outer_inset,
                fill=255,
            )
            inner_rim = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(inner_rim).rounded_rectangle(
                [(rim_inner_inset, rim_inner_inset), (btn_w - 1 - rim_inner_inset, btn_h - 1 - rim_inner_inset)],
                radius=max(btn_radius - rim_inner_inset, 0),
                fill=255,
            )
            ring_mask = ImageChops.subtract(outer_rim, inner_rim)

            # Directional weights
            # Left-to-right gradient (255 -> 0)
            grad_left = Image.new("L", (btn_w, btn_h), 0)
            dgl = ImageDraw.Draw(grad_left)
            for x in range(btn_w):
                a = int(255 * (1.0 - x / max(btn_w - 1, 1)))
                dgl.line([(x, 0), (x, btn_h)], fill=a)
            # Top-to-bottom gradient (255 -> 0)
            grad_top = Image.new("L", (btn_w, btn_h), 0)
            dgt = ImageDraw.Draw(grad_top)
            for y in range(btn_h):
                a = int(255 * (1.0 - y / max(btn_h - 1, 1)))
                dgt.line([(0, y), (btn_w, y)], fill=a)
            # Right and bottom gradients (0 -> 255)
            grad_right = ImageOps.invert(grad_left)
            grad_bottom = ImageOps.invert(grad_top)

            # Top-left light rim mask
            tl_mask = ImageChops.multiply(ring_mask, ImageChops.multiply(grad_left, grad_top))
            tl_mask = tl_mask.filter(ImageFilter.GaussianBlur(radius=0.9))
            tl_layer = Image.new("RGBA", (btn_w, btn_h), (255, 255, 255, 0))
            tl_layer.putalpha(tl_mask.point(lambda p: int(p * 0.24)))  # soften to avoid concave look
            btn.alpha_composite(tl_layer, (0, 0))

            # Bottom-right dark rim mask
            br_mask = ImageChops.multiply(ring_mask, ImageChops.multiply(grad_right, grad_bottom))
            br_mask = br_mask.filter(ImageFilter.GaussianBlur(radius=0.9))
            br_layer = Image.new("RGBA", (btn_w, btn_h), (10, 20, 70, 0))  # cool dark tone
            br_layer.putalpha(br_mask.point(lambda p: int(p * 0.14)))  # reduce dark rim to avoid 'dip' perception
            btn.alpha_composite(br_layer, (0, 0))

            # Step E: bevel stroke (subtle gradient stroke around the edge)
            stroke_outer_inset = 0
            stroke_inner_inset = 1
            stroke_outer = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(stroke_outer).rounded_rectangle(
                [(stroke_outer_inset, stroke_outer_inset), (btn_w - 1 - stroke_outer_inset, btn_h - 1 - stroke_outer_inset)],
                radius=btn_radius - stroke_outer_inset,
                fill=255,
            )
            stroke_inner = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(stroke_inner).rounded_rectangle(
                [(stroke_inner_inset, stroke_inner_inset), (btn_w - 1 - stroke_inner_inset, btn_h - 1 - stroke_inner_inset)],
                radius=max(btn_radius - stroke_inner_inset, 0),
                fill=255,
            )
            stroke_ring = ImageChops.subtract(stroke_outer, stroke_inner)

            # Light component (top-left)
            stroke_light_mask = ImageChops.multiply(stroke_ring, ImageChops.multiply(grad_left, grad_top))
            stroke_light = Image.new("RGBA", (btn_w, btn_h), (255, 255, 255, 0))
            stroke_light.putalpha(stroke_light_mask.point(lambda p: int(p * 0.35)))
            btn.alpha_composite(stroke_light, (0, 0))

            # Dark component (bottom-right)
            stroke_dark_mask = ImageChops.multiply(stroke_ring, ImageChops.multiply(grad_right, grad_bottom))
            stroke_dark = Image.new("RGBA", (btn_w, btn_h), (5, 17, 64, 0))
            stroke_dark.putalpha(stroke_dark_mask.point(lambda p: int(p * 0.45)))
            btn.alpha_composite(stroke_dark, (0, 0))

            # Step 5: edge chroma accents (very subtle modern glass vibe)
            # Use the 1px stroke ring but tint it directionally
            accent_cyan = (110, 231, 255)   # soft cyan
            accent_pink = (255, 122, 209)   # soft pink
            # Top-left cyan
            accent_cyan_mask = ImageChops.multiply(stroke_light_mask, ImageChops.multiply(grad_left, grad_top))
            accent_cyan_layer = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
            accent_cyan_layer.putalpha(accent_cyan_mask.point(lambda p: int(p * 0.12)))  # ~12%
            btn.alpha_composite(Image.new("RGBA", (btn_w, btn_h), (*accent_cyan, 0)).putalpha(accent_cyan_layer.split()[-1]) or accent_cyan_layer, (0, 0))
            # Bottom-right pink
            accent_pink_mask = ImageChops.multiply(stroke_dark_mask, ImageChops.multiply(grad_right, grad_bottom))
            accent_pink_layer = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
            accent_pink_layer.putalpha(accent_pink_mask.point(lambda p: int(p * 0.12)))  # ~12%
            btn.alpha_composite(Image.new("RGBA", (btn_w, btn_h), (*accent_pink, 0)).putalpha(accent_pink_layer.split()[-1]) or accent_pink_layer, (0, 0))

            # Text mask
            text_mask = Image.new("L", (btn_w, btn_h), 0)
            td = ImageDraw.Draw(text_mask)
            bbox = td.textbbox((0, 0), label, font=btn_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx, ty = (btn_w - tw) // 2, (btn_h - th) // 2
            td.text((tx, ty), label, fill=255, font=btn_font)

            # Gradient text fill: FFF3DD -> FFFFFF
            text_fill = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
            tgd = ImageDraw.Draw(text_fill)
            for y in range(btn_h):
                t = y / max(btn_h - 1, 1)
                r = int(txt_top[0] + (txt_bottom[0] - txt_top[0]) * t)
                g = int(txt_top[1] + (txt_bottom[1] - txt_top[1]) * t)
                b = int(txt_top[2] + (txt_bottom[2] - txt_top[2]) * t)
                tgd.line([(0, y), (btn_w, y)], fill=(r, g, b, 255))
            text_fill.putalpha(text_mask)
            btn.alpha_composite(text_fill, (0, 0))

            # Paste button onto panel
            px = (width - btn_w) // 2

            # Step 6: ambient blue glow under the button (soft, modern)
            glow_blur = 10
            glow_pad = glow_blur * 2
            glow_mask = Image.new("L", (btn_w + 2 * glow_pad, btn_h + 2 * glow_pad), 0)
            gmd = ImageDraw.Draw(glow_mask)
            gmd.rounded_rectangle(
                [(glow_pad, glow_pad), (glow_pad + btn_w - 1, glow_pad + btn_h - 1)],
                radius=btn_radius,
                fill=255,
            )
            glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(radius=glow_blur))
            glow_color = (29, 43, 161, 26)  # #1D2BA1 at ~10% alpha
            glow_rgba = Image.new("RGBA", glow_mask.size, glow_color)
            glow_rgba.putalpha(glow_mask)
            # Slight upward bias so it doesn't look like a shadow
            composed.alpha_composite(glow_rgba, (px - glow_pad, y_offset - glow_pad + 2))

            # Step B: soft drop shadow under the button (raised look)
            shadow_blur = 12
            shadow_offset_y = 6
            shadow_pad = shadow_blur * 2
            shadow_mask = Image.new("L", (btn_w + 2 * shadow_pad, btn_h + 2 * shadow_pad), 0)
            smd = ImageDraw.Draw(shadow_mask)
            smd.rounded_rectangle(
                [(shadow_pad, shadow_pad), (shadow_pad + btn_w - 1, shadow_pad + btn_h - 1)],
                radius=btn_radius,
                fill=255,
            )
            shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
            shadow_rgba = Image.new("RGBA", shadow_mask.size, (0, 0, 0, 0))
            # Slightly blue-tinted shadow to match theme
            shadow_color = (5, 17, 64, 120)
            shadow_rgba.paste(shadow_color, (0, 0), shadow_mask)
            composed.alpha_composite(shadow_rgba, (px - shadow_pad, y_offset + shadow_offset_y - shadow_pad))

            # Edge smoothing for button body
            btn_alpha_smoothed = btn.split()[-1].filter(ImageFilter.GaussianBlur(radius=0.35))
            btn.putalpha(btn_alpha_smoothed)

            # Final anti-halo crisp edge: 1px inner stroke in fill color to cover any light seam
            anti_halo = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
            ahd = ImageDraw.Draw(anti_halo)
            ahd.rounded_rectangle(
                [(1, 1), (btn_w - 2, btn_h - 2)],
                radius=btn_radius - 1,
                outline=(btn_fill_rgb[0], btn_fill_rgb[1], btn_fill_rgb[2], 255),
                width=1,
            )
            btn.alpha_composite(anti_halo, (0, 0))

            # Super-sampling smooth: upscale, lightly blur, then downscale for crisp anti-aliased edges
            smoothed_btn = (
                btn.resize((btn_w * 2, btn_h * 2), Image.LANCZOS)
                .filter(ImageFilter.GaussianBlur(radius=1.2))
                .resize((btn_w, btn_h), Image.LANCZOS)
            )

            composed.alpha_composite(smoothed_btn, (px, y_offset))

            # Add a final crisp edge ring slightly further inward to ensure full perimeter coverage
            edge_overlay = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
            edge_inset = rim_outer_inset + 1  # shift inward by 1px from the current rim
            edge_outer = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(edge_outer).rounded_rectangle(
                [(edge_inset, edge_inset), (btn_w - 1 - edge_inset, btn_h - 1 - edge_inset)],
                radius=btn_radius - edge_inset,
                fill=255,
            )
            edge_inner = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(edge_inner).rounded_rectangle(
                [(edge_inset + 1, edge_inset + 1), (btn_w - 2 - edge_inset, btn_h - 2 - edge_inset)],
                radius=max(btn_radius - (edge_inset + 1), 0),
                fill=255,
            )
            edge_ring = ImageChops.subtract(edge_outer, edge_inner).filter(ImageFilter.GaussianBlur(radius=0.6))
            # Directional split
            edge_light_mask = ImageChops.multiply(edge_ring, ImageChops.multiply(grad_left, grad_top))
            edge_dark_mask = ImageChops.multiply(edge_ring, ImageChops.multiply(grad_right, grad_bottom))
            # Composite
            edge_light = Image.new("RGBA", (btn_w, btn_h), (255, 255, 255, 0))
            edge_light.putalpha(edge_light_mask.point(lambda p: int(p * 0.10)))  # light 10%
            edge_overlay = Image.alpha_composite(edge_overlay, edge_light)
            edge_dark = Image.new("RGBA", (btn_w, btn_h), (10, 20, 70, 0))
            edge_dark.putalpha(edge_dark_mask.point(lambda p: int(p * 0.06)))   # dark 6%
            edge_overlay = Image.alpha_composite(edge_overlay, edge_dark)
            composed.alpha_composite(edge_overlay, (px, y_offset))

            # Build HOVER variant: base button + very subtle local specular only
            composed_hover.alpha_composite(smoothed_btn, (px, y_offset))
            hover_spec = Image.new("RGBA", (btn_w, btn_h), (255, 255, 255, 0))
            hover_mask = Image.new("L", (btn_w, btn_h), 0)
            hdraw = ImageDraw.Draw(hover_mask)
            hx, hy = int(btn_w * 0.30), int(btn_h * 0.30)
            hrx, hry = 26, 20
            hbox = (hx - hrx, hy - hry, hx + hrx, hy + hry)
            hdraw.ellipse(hbox, fill=70)  # peak ~27% before blur
            hover_mask = hover_mask.filter(ImageFilter.GaussianBlur(radius=6))
            # Clip to avoid spreading to edges
            hover_clip = Image.new("L", (btn_w, btn_h), 0)
            ImageDraw.Draw(hover_clip).rounded_rectangle(
                [(inset_hi, inset_hi), (btn_w - 1 - inset_hi, btn_h - 1 - inset_hi)],
                radius=btn_radius - inset_hi,
                fill=255,
            )
            hover_mask = ImageChops.multiply(hover_mask, hover_clip)
            hover_spec.putalpha(hover_mask.point(lambda p: int(p * 0.6)))  # soften overall
            composed_hover.alpha_composite(hover_spec, (px, y_offset))

            # Save button bbox for interactions
            button_bbox = (px, y_offset, px + btn_w, y_offset + btn_h)

            # Build pressed variant on composed_pressed
            shadow_blur_p = 8
            shadow_offset_y_p = 2
            shadow_pad_p = shadow_blur_p * 2
            shadow_mask_p = Image.new("L", (btn_w + 2 * shadow_pad_p, btn_h + 2 * shadow_pad_p), 0)
            smdp = ImageDraw.Draw(shadow_mask_p)
            smdp.rounded_rectangle(
                [(shadow_pad_p, shadow_pad_p), (shadow_pad_p + btn_w - 1, shadow_pad_p + btn_h - 1)],
                radius=btn_radius,
                fill=255,
            )
            shadow_mask_p = shadow_mask_p.filter(ImageFilter.GaussianBlur(radius=shadow_blur_p))
            shadow_rgba_p = Image.new("RGBA", shadow_mask_p.size, (0, 0, 0, 0))
            shadow_rgba_p.paste((5, 17, 64, 100), (0, 0), shadow_mask_p)
            composed_pressed.alpha_composite(shadow_rgba_p, (px - shadow_pad_p, y_offset + shadow_offset_y_p - shadow_pad_p))
            # Shift button down by 2px for pressed look
            composed_pressed.alpha_composite(smoothed_btn, (px, y_offset + 2))

    # Clip the entire panel to the same rounded shape (fully opaque inside)
    panel_mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(panel_mask).rounded_rectangle([(0, 0), (width, height)], radius=corner_radius, fill=255)
    composed.putalpha(panel_mask)
    if 'composed_hover' in locals():
        composed_hover.putalpha(panel_mask.copy())
    if 'composed_pressed' in locals():
        composed_pressed.putalpha(panel_mask.copy())

    photo = ImageTk.PhotoImage(composed)
    label = tk.Label(root, image=photo, bg="#1D2BA1", bd=0, highlightthickness=0)
    label.image = photo  # keep reference

    # If hover/pressed-state available, wire interactions
    if 'composed_hover' in locals() and 'composed_pressed' in locals() and button_bbox:
        photo_hover = ImageTk.PhotoImage(composed_hover)
        photo_pressed = ImageTk.PhotoImage(composed_pressed)
        label.photo_normal = photo
        label.photo_hover = photo_hover
        label.photo_pressed = photo_pressed
        label._button_bbox = button_bbox
        label._pressed = False

        def _inside_button(ev) -> bool:
            x, y = ev.x, ev.y
            x1, y1, x2, y2 = label._button_bbox
            return x1 <= x <= x2 and y1 <= y <= y2

        def _on_motion(ev):
            if label._pressed:
                return
            if _inside_button(ev):
                label.configure(image=label.photo_hover)
            else:
                label.configure(image=label.photo_normal)

        def _on_press(ev):
            if _inside_button(ev):
                label._pressed = True
                label.configure(image=label.photo_pressed)

        def _on_release(ev):
            label._pressed = False
            if _inside_button(ev):
                label.configure(image=label.photo_hover)
                try:
                    on_signin(root)
                except Exception:
                    pass
            else:
                label.configure(image=label.photo_normal)

        label.bind("<Motion>", _on_motion)
        label.bind("<Leave>", lambda e: (not label._pressed) and label.configure(image=label.photo_normal))
        label.bind("<ButtonPress-1>", _on_press)
        label.bind("<ButtonRelease-1>", _on_release)
        # Allow keyboard activation when focused
        label.configure(takefocus=1)
        label.bind("<Return>", lambda e: (_on_press(e), _on_release(e)))
        label.bind("<space>", lambda e: (_on_press(e), _on_release(e)))

    # Enable click-to-focus on username/password pills anywhere inside the pill shape
    if 'pill_bboxes' in locals() and pill_bboxes:
        label._pill_bboxes = pill_bboxes
        def _focus_pill(ev):
            x, y = ev.x, ev.y
            # Prefer username, then password
            ub = label._pill_bboxes.get("username")
            if ub and ub[0] <= x <= ub[2] and ub[1] <= y <= ub[3]:
                try:
                    root.entry_username.focus_set()
                    return "break"
                except Exception:
                    return
            pb = label._pill_bboxes.get("password")
            if pb and pb[0] <= x <= pb[2] and pb[1] <= y <= pb[3]:
                try:
                    root.entry_password.focus_set()
                    return "break"
                except Exception:
                    return
        # Use Button-1 (press). If another handler exists, both will run; returning "break" stops further handling
        label.bind("<Button-1>", _focus_pill, add="+")
    label.place(relx=0.5, rely=0.5, anchor="center")
    return label


def add_title_username(root: tk.Tk) -> Optional[tk.Widget]:
    """
    Adds the 'Username' title centered near the top of the glass panel:
    - Size 404x84
    - Opacity 90%
    - Duru Sans Regular 64 (falls back if font not available)
    - Vertical gradient fill: #FFFFFF -> #FFF3DD
    - Drop shadow: blur 25, black
    """
    width, height = 404, 84
    # Try to load Duru Sans from ./assets/fonts/DuruSans-Regular.ttf
    fonts_dir = Path(__file__).parent / "assets" / "fonts"
    duru_path = fonts_dir / "DuruSans-Regular.ttf"
    if duru_path.exists():
        font = ImageFont.truetype(str(duru_path), 64)
    else:
        # Fallback font available on Windows
        font = ImageFont.truetype("segoeui.ttf", 64) if Path("C:/Windows/Fonts/segoeui.ttf").exists() else ImageFont.load_default()

    # Create text mask
    text = "Username"
    text_img = Image.new("L", (width, height), 0)
    draw_mask = ImageDraw.Draw(text_img)
    # Measure text and center
    bbox = draw_mask.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    tx = (width - text_w) // 2
    ty = (height - text_h) // 2
    draw_mask.text((tx, ty), text, fill=255, font=font)

    # Gradient fill (vertical)
    start_rgb = (0xFF, 0xFF, 0xFF)   # #FFFFFF
    end_rgb = (0xFF, 0xF3, 0xDD)     # #FFF3DD
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(gradient)
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
        g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
        b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
        gdraw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    gradient.putalpha(text_img.point(lambda p: int(p * 0.90)))  # 90% opacity overall

    # Drop shadow (blurred black under text)
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_mask = text_img.filter(ImageFilter.GaussianBlur(radius=25))
    shadow.putalpha(shadow_mask)

    composed = Image.alpha_composite(shadow, gradient)

    photo = ImageTk.PhotoImage(composed)
    label = tk.Label(root, image=photo, bg="#1D2BA1", bd=0, highlightthickness=0)
    label.image = photo  # keep reference

    # Position: centered horizontally over the panel, near its top
    window_w, window_h = 1400, 1024
    panel_w, panel_h = 793, 869
    panel_cx, panel_cy = window_w // 2, window_h // 2
    panel_top = panel_cy - panel_h // 2
    y = panel_top + 90  # top margin inside the panel
    label.place(x=panel_cx, y=y, anchor="n")
    return label


def create_splash_overlay(root: tk.Tk, width: int, height: int, bg: str = "#1D2BA1") -> tk.Toplevel:
    """
    Creates a borderless overlay window exactly covering the main window.
    The overlay will be used for the logo fade-in sequence.
    """
    # Make sure root has a finalized position/sizing
    root.update_idletasks()

    overlay = tk.Toplevel(root)
    overlay.overrideredirect(True)
    overlay.configure(bg=bg)
    overlay.attributes("-alpha", 1.0)
    overlay.lift()
    overlay.attributes("-topmost", True)

    def place_overlay() -> None:
        # Align overlay to the root's on-screen position
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        overlay.geometry(f"{width}x{height}+{x}+{y}")

    # Initial placement and keep it aligned on root moves/resizes (debounced)
    place_overlay()
    def on_configure(_e=None):
        if getattr(overlay, "_place_after_id", None):
            overlay.after_cancel(overlay._place_after_id)
        overlay._place_after_id = overlay.after(40, place_overlay)
    root.bind("<Configure>", on_configure)

    # Placeholder container for future logo content
    holder = tk.Frame(overlay, bg=bg, width=width, height=height, bd=0, highlightthickness=0)
    holder.place(x=0, y=0)

    # Allow quick skip with Esc or click
    overlay.bind("<Escape>", lambda e: overlay.destroy())
    overlay.bind("<Button-1>", lambda e: overlay.destroy())

    return overlay

def create_panel_reveal_overlay(root: tk.Tk, width: int, height: int, bg: str = "#1D2BA1") -> tk.Toplevel:
    """
    Creates a full-window cover overlay used to 'reveal' the panel by fading OUT.
    Starts fully opaque (alpha=1.0) and sits on top of the app until faded away.
    """
    root.update_idletasks()

    cover = tk.Toplevel(root)
    cover.overrideredirect(True)
    cover.configure(bg=bg)
    cover.attributes("-alpha", 1.0)
    cover.lift()
    cover.attributes("-topmost", True)
    cover.transient(root)

    def place_cover() -> None:
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        cover.geometry(f"{width}x{height}+{x}+{y}")

    place_cover()

    def on_configure(_e=None):
        if getattr(cover, "_place_after_id", None):
            cover.after_cancel(cover._place_after_id)
        cover._place_after_id = cover.after(40, place_cover)

    root.bind("<Configure>", on_configure)

    holder = tk.Frame(cover, bg=bg, width=width, height=height, bd=0, highlightthickness=0)
    holder.place(x=0, y=0)

    return cover

def set_overlay_logo(
    overlay: tk.Toplevel,
    image_path: str,
    opacity: float = 0.8,
    max_width_ratio: float = 0.55,
    max_height_ratio: float = 0.55,
) -> Optional[tk.Widget]:
    """
    Renders the logo centered on the splash overlay with the given opacity.
    Scales the image to fit within the provided width/height ratios.
    """
    try:
        overlay.update_idletasks()
        ow, oh = overlay.winfo_width(), overlay.winfo_height()

        # Load and scale logo
        img = Image.open(image_path).convert("RGBA")
        target_w = int(ow * max_width_ratio)
        target_h = int(oh * max_height_ratio)
        img = ImageOps.contain(img, (target_w, target_h), Image.LANCZOS)

        # Apply desired opacity
        r, g, b, a = img.split()
        a = a.point(lambda p: int(p * max(0.0, min(1.0, opacity))))
        img.putalpha(a)

        photo = ImageTk.PhotoImage(img)
        label = tk.Label(overlay, image=photo, bg=overlay["bg"], bd=0, highlightthickness=0)
        label.image = photo  # keep reference
        label.place(relx=0.5, rely=0.5, anchor="center")
        overlay._logo_label = label  # keep reference on overlay
        overlay._logo_rgba = img      # store original RGBA image for animating
        return label
    except FileNotFoundError:
        # Minimal fallback
        fallback = tk.Label(overlay, text="Logo not found", fg="white", bg=overlay["bg"])
        fallback.place(relx=0.5, rely=0.5, anchor="center")
        overlay._logo_label = fallback
        return fallback

def fade_out_overlay(overlay: tk.Toplevel, duration_ms: int = 1200, steps: int = 24, on_finished=None) -> None:
    """
    Smoothly fades out the overlay window and destroys it at the end.
    """
    try:
        current_alpha = float(overlay.attributes("-alpha"))
    except Exception:
        current_alpha = 1.0

    steps = max(1, int(steps))
    step_ms = max(10, int(duration_ms / steps))
    delta = current_alpha / steps

    def step(i: int = 0) -> None:
        # If overlay was already destroyed, stop
        if not overlay.winfo_exists():
            return
        new_alpha = max(0.0, current_alpha - delta * i)
        overlay.attributes("-alpha", new_alpha)
        if new_alpha <= 0.0:
            try:
                overlay.destroy()
            finally:
                if on_finished:
                    on_finished()
            return
        overlay.after(step_ms, lambda: step(i + 1))

    step(0)


def fade_logo_then_window(
    overlay: tk.Toplevel,
    logo_duration_ms: int = 700,
    logo_steps: int = 24,
    window_duration_ms: int = 700,
    window_steps: int = 30,
) -> None:
    """
    Phase 1: Fade the logo label's image alpha to 0 while keeping the overlay fully opaque.
    Phase 2: Fade the overlay window out to reveal the app.
    """
    # Phase 1 - fade logo image if present
    logo_label = getattr(overlay, "_logo_label", None)
    logo_img = getattr(overlay, "_logo_rgba", None)
    if logo_label is None or logo_img is None:
        # Fallback: just fade the window
        fade_out_overlay(overlay, duration_ms=window_duration_ms, steps=window_steps)
        return

    steps = max(1, int(logo_steps))
    step_ms = max(10, int(logo_duration_ms / steps))

    def update_logo(step_idx: int = 0):
        if not overlay.winfo_exists():
            return
        t = min(1.0, step_idx / steps)
        # scale alpha by (1 - t)
        r, g, b, a = logo_img.split()
        a_scaled = a.point(lambda p: int(p * (1.0 - t)))
        img_scaled = Image.merge("RGBA", (r, g, b, a_scaled))
        photo = ImageTk.PhotoImage(img_scaled)
        logo_label.configure(image=photo)
        logo_label.image = photo
        if t >= 1.0:
            # Phase 2 - fade the window away
            fade_out_overlay(overlay, duration_ms=window_duration_ms, steps=window_steps)
            return
        overlay.after(step_ms, lambda: update_logo(step_idx + 1))

    # Ensure overlay stays fully opaque during logo fade
    try:
        overlay.attributes("-alpha", 1.0)
    except Exception:
        pass
    update_logo(0)

def add_signin_button_widget(root: tk.Tk) -> Optional[tk.Widget]:
    """
    Draws the 'Sign in' button as its own widget layered on top of the glass panel.
    Size: 339x101, fill #051140, text gradient #FFF3DD -> #FFFFFF.
    """
    btn_w, btn_h = 339, 101
    btn_radius = 50
    btn_fill_rgb = (0x05, 0x11, 0x40)  # #051140
    txt_top = (0xFF, 0xF3, 0xDD)
    txt_bottom = (0xFF, 0xFF, 0xFF)

    # Preferred font
    fonts_dir = Path(__file__).parent / "assets" / "fonts"
    duru_path = fonts_dir / "DuruSans-Regular.ttf"
    if duru_path.exists():
        btn_font = ImageFont.truetype(str(duru_path), 48)
    else:
        btn_font = ImageFont.truetype("segoeui.ttf", 48) if Path("C:/Windows/Fonts/segoeui.ttf").exists() else ImageFont.load_default()

    # Draw button image
    btn = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
    mask = Image.new("L", (btn_w, btn_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (btn_w - 1, btn_h - 1)], radius=btn_radius, fill=255)

    base_btn = Image.new("RGBA", (btn_w, btn_h), (*btn_fill_rgb, 255))
    base_btn.putalpha(mask)
    btn.alpha_composite(base_btn, (0, 0))

    # Soft top highlight
    hi = Image.new("RGBA", (btn_w, btn_h), (255, 255, 255, 0))
    grad = Image.new("L", (btn_w, btn_h), 0)
    gd = ImageDraw.Draw(grad)
    cutoff = int(btn_h * 0.45)
    for y in range(cutoff):
        a = int(120 * (1.0 - y / max(cutoff - 1, 1)))
        gd.line([(0, y), (btn_w, y)], fill=a)
    grad = ImageChops.multiply(grad, mask)
    hi.putalpha(grad)
    btn.alpha_composite(hi, (0, 0))

    # Text
    text = "Sign in"
    text_mask = Image.new("L", (btn_w, btn_h), 0)
    td = ImageDraw.Draw(text_mask)
    bbox = td.textbbox((0, 0), text, font=btn_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = (btn_w - tw) // 2, (btn_h - th) // 2
    td.text((tx, ty), text, fill=255, font=btn_font)

    text_fill = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
    tgd = ImageDraw.Draw(text_fill)
    for y in range(btn_h):
        t = y / max(btn_h - 1, 1)
        r = int(txt_top[0] + (txt_bottom[0] - txt_top[0]) * t)
        g = int(txt_top[1] + (txt_bottom[1] - txt_top[1]) * t)
        b = int(txt_top[2] + (txt_bottom[2] - txt_top[2]) * t)
        tgd.line([(0, y), (btn_w, y)], fill=(r, g, b, 255))
    text_fill.putalpha(text_mask)
    btn.alpha_composite(text_fill, (0, 0))

    photo = ImageTk.PhotoImage(btn)
    label = tk.Label(root, image=photo, bg="#1D2BA1", bd=0, highlightthickness=0)
    label.image = photo  # keep reference

    # Place centered at bottom of panel
    window_w, window_h = 1400, 1024
    panel_w, panel_h = 793, 869
    panel_cx, panel_cy = window_w // 2, window_h // 2
    panel_top = panel_cy - panel_h // 2
    y = panel_top + panel_h - btn_h - 70
    label.place(x=panel_cx, y=y, anchor="n")
    return label


def add_interactive_entries(root: tk.Tk) -> None:
    """
    Creates real Entry widgets positioned exactly over the username/password pills.
    Minimal styling to blend into the pill fill (#9CA2BC). Includes placeholder behavior.
    """
    # Geometry consistent with how the panel and pills were drawn
    window_w, window_h = 1400, 1024
    panel_w, panel_h = 793, 869
    pill_w, pill_h = 696, 90
    # Panel absolute position
    panel_cx, panel_cy = window_w // 2, window_h // 2
    panel_left = panel_cx - panel_w // 2
    panel_top = panel_cy - panel_h // 2
    # Pill offsets used during drawing
    username_y_offset = 235
    password_y_offset = 485
    pill_left_in_panel = (panel_w - pill_w) // 2

    # Entry rect slightly inset so the pill edges remain visible
    inset_x = 20
    entry_x = panel_left + pill_left_in_panel + inset_x
    entry_width = pill_w - inset_x * 2

    # Font
    fonts_dir = Path(__file__).parent / "assets" / "fonts"
    duru_path = fonts_dir / "DuruSans-Regular.ttf"
    if duru_path.exists():
        entry_font = (str(duru_path), 20)  # tk doesn't accept TTF path directly; will fallback to tk font loader
        try:
            # Use PIL truetype metrics to pick size; Tk will fallback if needed
            _ = ImageFont.truetype(str(duru_path), 20)
            entry_font = ("Duru Sans", 20)
        except Exception:
            entry_font = ("Segoe UI", 20)
    else:
        entry_font = ("Segoe UI", 20)

    # Common style
    entry_kwargs = dict(
        bd=0,
        relief="flat",
        highlightthickness=0,
        bg="#9CA2BC",
        fg="white",
        insertbackground="white",
        justify="center",
        font=entry_font,
    )

    # Helper: placeholder behavior
    def set_placeholder(entry: tk.Entry, var: tk.StringVar, text: str, is_password: bool = False) -> None:
        entry._placeholder_text = text
        entry._is_password_field = is_password
        entry._has_placeholder = True
        var.set(text)
        entry.config(fg="#E6E6E6", show="")  # show placeholder plainly

        def on_focus_in(_e):
            if entry._has_placeholder:
                var.set("")
                entry.config(fg="white", show=("•" if is_password else ""))
                entry._has_placeholder = False

        def on_focus_out(_e):
            if not var.get():
                var.set(text)
                entry.config(fg="#E6E6E6", show="")
                entry._has_placeholder = True

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    # Username Entry
    e_user = tk.Entry(root, textvariable=root.username_var, **entry_kwargs)
    # Vertical placement: roughly center in pill (Entry height ~ one line)
    e_user_y = panel_top + username_y_offset + (pill_h - 28) // 2
    e_user.place(x=entry_x, y=e_user_y, width=entry_width)
    set_placeholder(e_user, root.username_var, "Enter username", is_password=False)
    root.entry_username = e_user
    # Enter in username moves focus to password
    e_user.bind("<Return>", lambda _e: root.entry_password.focus_set())

    # Password Entry
    e_pass = tk.Entry(root, textvariable=root.password_var, **entry_kwargs)
    e_pass_y = panel_top + password_y_offset + (pill_h - 28) // 2
    e_pass.place(x=entry_x, y=e_pass_y, width=entry_width)
    set_placeholder(e_pass, root.password_var, "Enter password", is_password=True)
    root.entry_password = e_pass

    # Enter key triggers sign-in from password field
    e_pass.bind("<Return>", lambda _e: on_signin(root))

    # Enable Esc to clear fields
    root.bind("<Escape>", lambda _e: clear_fields(root))


def on_signin(root: tk.Tk) -> None:
    """
    Sign-in handler: validates credentials and transitions to the Available Devices window.
    Accepts any non-empty values for this prototype.
    """
    # Treat placeholders as empty
    username = root.username_var.get().strip()
    password = root.password_var.get()
    if getattr(root, "entry_username", None) is not None and getattr(root.entry_username, "_has_placeholder", False):
        username = ""
    if getattr(root, "entry_password", None) is not None and getattr(root.entry_password, "_has_placeholder", False):
        password = ""

    if not username or not password:
        messagebox.showwarning("Sign in", "Please enter a username and password.")
        return

    # Prototype success
    print(f"[SignIn] username='{username}' - Authentication successful")
    
    # Store credentials for the next window if needed
    root._signin_username = username
    
    # Close the signin window and launch the main application
    root.destroy()
    
    # Launch the Available Devices window (PyQt6)
    launch_main_application(username)


def launch_main_application(username: str = "") -> None:
    """
    Launch the Available Devices window using PyQt6.
    Called after successful sign-in.
    """
    from PyQt6.QtWidgets import QApplication
    from Host_Team.Host.gui.availableDevices import MainWindow
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.setWindowTitle(f"Available Devices - {username}" if username else "Available Devices")
    window.show()
    sys.exit(app.exec())


def clear_fields(root: tk.Tk) -> None:
    root.username_var.set("")
    root.password_var.set("")
    if getattr(root, "entry_username", None) is not None:
        root.entry_username.delete(0, "end")
        # reapply placeholder if needed
        root.entry_username.event_generate("<FocusOut>")
    if getattr(root, "entry_password", None) is not None:
        root.entry_password.delete(0, "end")
        root.entry_password.event_generate("<FocusOut>")

if __name__ == "__main__":
    app = create_signin_window()
    app.mainloop()

