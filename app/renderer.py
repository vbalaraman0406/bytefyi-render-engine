import math
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")

_FONT_CACHE: Dict[Tuple[str, str, int], ImageFont.FreeTypeFont] = {}
_IMAGE_CACHE: Dict[str, Image.Image] = {}


def get_font(font_family: str, font_weight: str, size_px: int) -> ImageFont.FreeTypeFont:
    """Resolve bundled Inter / InterDisplay TrueType font with caching."""
    w_str = str(font_weight or "400").strip().lower()
    key = (font_family or "Inter", w_str, size_px)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    weight_num = 400
    if w_str in ("bold", "700"):
        weight_num = 700
    elif w_str in ("extrabold", "800"):
        weight_num = 800
    elif w_str in ("black", "900"):
        weight_num = 900
    elif w_str in ("semibold", "600"):
        weight_num = 600
    elif w_str in ("medium", "500"):
        weight_num = 500
    else:
        try:
            weight_num = int(w_str)
        except ValueError:
            weight_num = 400

    use_display = size_px >= 54
    prefix = "InterDisplay" if use_display else "Inter"
    if weight_num >= 900:
        fname = f"{prefix}-Black.ttf"
    elif weight_num >= 800:
        fname = f"{prefix}-ExtraBold.ttf"
    elif weight_num >= 700:
        fname = f"{prefix}-Bold.ttf"
    elif weight_num >= 600:
        fname = f"{prefix}-SemiBold.ttf"
    elif weight_num >= 500:
        fname = f"{prefix}-Medium.ttf"
    else:
        fname = f"{prefix}-Regular.ttf"

    fpath = os.path.join(FONTS_DIR, fname)
    if not os.path.exists(fpath):
        fpath = os.path.join(FONTS_DIR, "Inter-Bold.ttf")

    font = ImageFont.truetype(fpath, max(8, size_px))
    _FONT_CACHE[key] = font
    return font


def parse_dim(val: Any, ref: float, default: float = 0.0) -> float:
    """Parse timeline dimension ('50%', '540px', 540) relative to ref."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return default
    if s.endswith("%"):
        try:
            return (float(s[:-1]) / 100.0) * ref
        except ValueError:
            return default
    if s.endswith("px"):
        s = s[:-2].strip()
    try:
        return float(s)
    except ValueError:
        return default


def parse_color(color_str: Optional[str], opacity_mult: float = 1.0) -> Tuple[int, int, int, int]:
    """Parse hex (#RGB, #RRGGBB, #RRGGBBAA) or rgba() color string into (R, G, B, A) tuple."""
    if not color_str:
        return (0, 0, 0, 0)
    s = str(color_str).strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            r, g, b = (int(c * 2, 16) for c in h)
            a = 255
        elif len(h) == 6:
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            a = 255
        elif len(h) == 8:
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            a = int(h[6:8], 16)
        else:
            return (255, 255, 255, int(255 * opacity_mult))
        return (r, g, b, max(0, min(255, int(round(a * opacity_mult)))))

    m = re.match(r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)", s, re.I)
    if m:
        r = int(float(m.group(1)))
        g = int(float(m.group(2)))
        b = int(float(m.group(3)))
        a_val = float(m.group(4)) if m.group(4) is not None else 1.0
        a = int(round((a_val * 255 if a_val <= 1.0 else a_val) * opacity_mult))
        return (
            max(0, min(255, r)),
            max(0, min(255, g)),
            max(0, min(255, b)),
            max(0, min(255, a)),
        )
    return (255, 255, 255, int(255 * opacity_mult))


def draw_vector_icon(
    draw: ImageDraw.ImageDraw,
    icon_type: str,
    cx: float,
    cy: float,
    size: float,
    opacity: float = 1.0,
) -> None:
    """Draw anti-aliased broadcast vector icons for ⚡, 🟢, and 🎙️."""
    if icon_type == "bolt":
        h = size * 0.95
        w = size * 0.65
        pts = [
            (cx + w * 0.12, cy - h * 0.50),
            (cx - w * 0.48, cy + h * 0.06),
            (cx - w * 0.04, cy + h * 0.06),
            (cx - w * 0.18, cy + h * 0.50),
            (cx + w * 0.48, cy - h * 0.08),
            (cx + w * 0.04, cy - h * 0.08),
        ]
        draw.polygon(pts, fill=parse_color("#FACC15", opacity))
    elif icon_type == "green_dot":
        r_outer = size * 0.46
        r_inner = size * 0.28
        draw.ellipse(
            [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
            fill=parse_color("rgba(16, 185, 129, 0.28)", opacity),
        )
        draw.ellipse(
            [cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
            fill=parse_color("#10B981", opacity),
        )
        r_spec = size * 0.09
        draw.ellipse(
            [
                cx - r_inner * 0.45,
                cy - r_inner * 0.45,
                cx - r_inner * 0.45 + r_spec * 2,
                cy - r_inner * 0.45 + r_spec * 2,
            ],
            fill=parse_color("rgba(255, 255, 255, 0.75)", opacity),
        )
    elif icon_type == "mic":
        c_cyan = parse_color("#38BDF8", opacity)
        mw = size * 0.34
        mh = size * 0.52
        top_y = cy - size * 0.44
        draw.rounded_rectangle(
            [cx - mw / 2, top_y, cx + mw / 2, top_y + mh],
            radius=mw / 2,
            fill=c_cyan,
        )
        arc_w = size * 0.56
        arc_top = cy - size * 0.22
        arc_bot = cy + size * 0.22
        draw.arc(
            [cx - arc_w / 2, arc_top, cx + arc_w / 2, arc_bot],
            start=0,
            end=180,
            fill=c_cyan,
            width=max(2, int(size * 0.09)),
        )
        stem_top = arc_bot
        stem_bot = cy + size * 0.42
        sw = max(2, int(size * 0.09))
        draw.line([(cx, stem_top), (cx, stem_bot)], fill=c_cyan, width=sw)
        bw = size * 0.36
        draw.line([(cx - bw / 2, stem_bot), (cx + bw / 2, stem_bot)], fill=c_cyan, width=sw)


def extract_leading_icon(text: str) -> Tuple[Optional[str], str]:
    """Detect and strip leading emoji that Inter font lacks so we can draw a crisp vector icon."""
    s = text.strip()
    if s.startswith("⚡"):
        return "bolt", s[1:].lstrip()
    if s.startswith("🟢"):
        return "green_dot", s[1:].lstrip()
    if s.startswith("🎙️"):
        return "mic", s[2:].lstrip()
    if s.startswith("🎙"):
        return "mic", s[1:].lstrip()
    return None, text


def wrap_text_lines(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: float,
) -> List[str]:
    """Word-wrap text within max_width while preserving explicit newlines."""
    paragraphs = text.split("\n")
    lines: List[str] = []
    for para in paragraphs:
        words = para.split(" ")
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            candidate = f"{cur} {w}" if cur else w
            bbox = font.getbbox(candidate)
            w_px = (bbox[2] - bbox[0]) if bbox else 0
            if w_px <= max_width or not cur:
                cur = candidate
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def render_shape_layer(
    canvas: Image.Image,
    el: Dict[str, Any],
    W: int,
    H: int,
    opacity: float = 1.0,
    y_offset: float = 0.0,
) -> None:
    """Render a shape element onto RGB canvas with true RGBA alpha blending & 2x supersampling."""
    w = parse_dim(el.get("width"), W, W)
    h = parse_dim(el.get("height"), H, H)
    cx = parse_dim(el.get("x"), W, W / 2.0)
    cy = parse_dim(el.get("y"), H, H / 2.0) + y_offset
    x_anchor = parse_dim(el.get("x_anchor"), 1.0, 0.5)
    y_anchor = parse_dim(el.get("y_anchor"), 1.0, 0.5)

    left = cx - w * x_anchor
    top = cy - h * y_anchor
    right = left + w
    bottom = top + h

    fill_rgba = parse_color(el.get("fill_color"), opacity)
    raw_stroke_color = el.get("stroke_color") or el.get("border_color")
    raw_stroke_width = el.get("stroke_width") if el.get("stroke_width") is not None else el.get("border_width")
    stroke_rgba = parse_color(raw_stroke_color, opacity) if raw_stroke_color else (0, 0, 0, 0)
    stroke_w = parse_dim(raw_stroke_width, W, 0.0)
    radius = parse_dim(el.get("border_radius"), min(w, h), 0.0)
    if "A 50 50" in str(el.get("path") or ""):
        radius = min(w, h) / 2.0

    # Full-canvas solid background
    if left <= 0 and top <= 0 and right >= W and bottom >= H and radius == 0:
        draw = ImageDraw.Draw(canvas, "RGBA")
        draw.rectangle([0, 0, W, H], fill=fill_rgba)
        return

    # Crisp thin grid lines / VWAP line
    if (w <= 4 or h <= 4) and radius == 0:
        draw = ImageDraw.Draw(canvas, "RGBA")
        if h == 3 and str(el.get("fill_color", "")).upper() == "#FACC15":
            glow_c = parse_color("rgba(250, 204, 21, 0.18)", opacity)
            draw.rectangle([int(left), int(top - 3), int(right), int(bottom + 3)], fill=glow_c)
        draw.rectangle(
            [int(round(left)), int(round(top)), int(round(right)), int(round(bottom))],
            fill=fill_rgba,
        )
        return

    pad = int(math.ceil(stroke_w + 10))
    p_left = max(0, int(math.floor(left - pad)))
    p_top = max(0, int(math.floor(top - pad)))
    p_right = min(W, int(math.ceil(right + pad)))
    p_bot = min(H, int(math.ceil(bottom + pad)))
    pw = p_right - p_left
    ph = p_bot - p_top
    if pw <= 0 or ph <= 0:
        return

    scale = 2
    patch = Image.new("RGBA", (pw * scale, ph * scale), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(patch, "RGBA")

    rx0 = (left - p_left) * scale
    ry0 = (top - p_top) * scale
    rx1 = (right - p_left) * scale
    ry1 = (bottom - p_top) * scale
    rr = radius * scale
    sw = int(round(stroke_w * scale))

    if 28 <= w <= 36 and radius == 4 and fill_rgba[3] > 200:
        glow_col = (fill_rgba[0], fill_rgba[1], fill_rgba[2], int(36 * opacity))
        pdraw.rounded_rectangle(
            [rx0 - 4, ry0 - 4, rx1 + 4, ry1 + 4],
            radius=rr + 4,
            fill=glow_col,
        )

    pdraw.rounded_rectangle(
        [rx0, ry0, rx1, ry1],
        radius=rr,
        fill=fill_rgba,
        outline=stroke_rgba if sw > 0 else None,
        width=sw if sw > 0 else 1,
    )

    smooth_patch = patch.resize((pw, ph), resample=Image.Resampling.LANCZOS)
    canvas.paste(smooth_patch, (p_left, p_top), smooth_patch)


def render_text_layer(
    canvas: Image.Image,
    el: Dict[str, Any],
    W: int,
    H: int,
    opacity: float = 1.0,
    y_offset: float = 0.0,
) -> None:
    """Render a text element onto RGB canvas with bundled Inter typography and vector icons."""
    raw_text = str(el.get("text") or "")
    if not raw_text.strip():
        return

    w = parse_dim(el.get("width"), W, W * 0.86)
    cx = parse_dim(el.get("x"), W, W / 2.0)
    cy = parse_dim(el.get("y"), H, H / 2.0) + y_offset

    x_anchor = parse_dim(el.get("x_anchor"), 1.0, 0.5)
    y_anchor = parse_dim(el.get("y_anchor"), 1.0, 0.5)

    font_size = int(round(parse_dim(el.get("font_size"), H, 28.0)))
    font_family = str(el.get("font_family") or "Inter")
    font_weight = str(el.get("font_weight") or "700")
    font = get_font(font_family, font_weight, font_size)

    line_height_mult = parse_dim(el.get("line_height"), 1.0, 1.22)
    if line_height_mult <= 0:
        line_height_mult = 1.22

    icon_type, clean_text = extract_leading_icon(raw_text)
    icon_advance = (font_size * 1.15) if icon_type else 0.0

    lines = wrap_text_lines(clean_text, font, max(60.0, w - icon_advance))
    line_px = font_size * line_height_mult
    total_text_h = font_size + max(0, len(lines) - 1) * line_px

    h = parse_dim(el.get("height"), H, total_text_h)
    box_left = cx - w * x_anchor
    box_top = cy - h * y_anchor

    t_align = str(el.get("text_alignment") or "").strip().lower()
    if not t_align:
        x_al = parse_dim(el.get("x_alignment"), 1.0, 0.5)
        if x_al <= 0.15:
            t_align = "left"
        elif x_al >= 0.85:
            t_align = "right"
        else:
            t_align = "center"

    y_align = parse_dim(el.get("y_alignment"), 1.0, 0.5)
    fill_rgba = parse_color(el.get("fill_color", "#FFFFFF"), opacity)

    if y_align <= 0.15:
        start_y = box_top
    elif y_align >= 0.85:
        start_y = box_top + h - total_text_h
    else:
        start_y = box_top + (h - total_text_h) / 2.0

    draw = ImageDraw.Draw(canvas, "RGBA")

    for idx, line in enumerate(lines):
        bbox = font.getbbox(line) if line else (0, 0, 0, font_size)
        lw = (bbox[2] - bbox[0]) if bbox else 0
        top_trim = bbox[1] if bbox else 0

        eff_w = lw + (icon_advance if idx == 0 else 0.0)
        if t_align == "left":
            line_x = box_left
        elif t_align == "right":
            line_x = box_left + w - eff_w
        else:
            line_x = box_left + (w - eff_w) / 2.0

        line_y = start_y + idx * line_px

        if idx == 0 and icon_type:
            icon_cx = line_x + font_size * 0.45
            icon_cy = line_y + font_size * 0.52
            draw_vector_icon(draw, icon_type, icon_cx, icon_cy, font_size * 0.92, opacity=opacity)
            text_x = line_x + icon_advance
        else:
            text_x = line_x

        draw.text((text_x, line_y - top_trim * 0.35), line, font=font, fill=fill_rgba)


def render_image_layer(
    canvas: Image.Image,
    el: Dict[str, Any],
    W: int,
    H: int,
    opacity: float = 1.0,
    y_offset: float = 0.0,
) -> None:
    """Render an external/cached image element onto RGB canvas with optional border_radius."""
    src_url = el.get("source")
    if not src_url:
        return
    try:
        if src_url not in _IMAGE_CACHE:
            req = urllib.request.Request(src_url, headers={"User-Agent": "ByteFYIRenderEngine/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            tmp_f = tempfile.NamedTemporaryFile(delete=False, suffix=".img")
            tmp_f.write(data)
            tmp_f.close()
            _IMAGE_CACHE[src_url] = Image.open(tmp_f.name).convert("RGBA")
            os.unlink(tmp_f.name)
        img = _IMAGE_CACHE[src_url]
        w = max(1, int(round(parse_dim(el.get("width"), W, img.width))))
        h = max(1, int(round(parse_dim(el.get("height"), H, img.height))))
        cx = parse_dim(el.get("x"), W, W / 2.0)
        cy = parse_dim(el.get("y"), H, H / 2.0) + y_offset

        fit_mode = str(el.get("fit") or "cover").lower()
        if fit_mode == "contain":
            scale = min(w / float(img.width), h / float(img.height))
            nw = max(1, int(round(img.width * scale)))
            nh = max(1, int(round(img.height * scale)))
            resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
            left = int(round(cx - nw / 2.0))
            top = int(round(cy - nh / 2.0))
        else:
            resized = img.resize((w, h), Image.Resampling.LANCZOS)
            left = int(round(cx - w / 2.0))
            top = int(round(cy - h / 2.0))

        radius = parse_dim(el.get("border_radius"), min(resized.width, resized.height), 0.0)
        if radius > 0:
            mask = Image.new("L", resized.size, 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.rounded_rectangle([0, 0, resized.width, resized.height], radius=radius, fill=255)
            r, g, b, a = resized.split()
            a = Image.composite(a, Image.new("L", resized.size, 0), mask)
            resized = Image.merge("RGBA", (r, g, b, a))

        if opacity < 1.0:
            r, g, b, a = resized.split()
            a = a.point(lambda p: int(p * opacity))
            resized = Image.merge("RGBA", (r, g, b, a))
        canvas.paste(resized, (left, top), resized)
    except Exception as exc:
        print(f"[renderer] Image load warning ({src_url}): {exc}")


def draw_scene_progress_bar(frame: Image.Image, W: int, prog: float) -> None:
    """Draw smooth live progress indicator inside the AI Desk Note card."""
    draw = ImageDraw.Draw(frame, "RGBA")
    bar_left = 90
    bar_right = W - 90
    bar_y = 1716
    draw.rounded_rectangle(
        [bar_left, bar_y, bar_right, bar_y + 5],
        radius=2,
        fill=(51, 65, 85, 130),
    )
    fill_w = max(6, int((bar_right - bar_left) * prog))
    draw.rounded_rectangle(
        [bar_left, bar_y, bar_left + fill_w, bar_y + 5],
        radius=2,
        fill=(56, 189, 248, 235),
    )


def render_composite_frame_at_time(
    t: float,
    visual_elements: List[Dict[str, Any]],
    bg_canvas: Image.Image,
    W: int,
    H: int,
    scene_windows: List[Tuple[float, float]],
    show_desk_progress: bool = False,
) -> Image.Image:
    """Render a single composite RGB frame at timestamp t (seconds)."""
    frame = bg_canvas.copy()
    for el in visual_elements:
        el_t = float(el.get("time") or 0.0)
        el_d = float(el.get("duration") or 0.0)
        if t < el_t or t >= (el_t + el_d - 1e-4):
            continue

        rel_t = t - el_t
        opacity = 1.0
        y_offset = 0.0

        anims = el.get("animations") or []
        for anim in anims:
            a_dur = float(anim.get("duration") or 0.25)
            if a_dur > 0 and rel_t < a_dur:
                p = max(0.0, min(1.0, rel_t / a_dur))
                eased = 1.0 - (1.0 - p) ** 3
                opacity *= eased
                y_offset += (1.0 - eased) * 10.0

        etype = el.get("type")
        if etype == "shape":
            render_shape_layer(frame, el, W, H, opacity=opacity, y_offset=y_offset)
        elif etype == "text":
            render_text_layer(frame, el, W, H, opacity=opacity, y_offset=y_offset)
        elif etype == "image":
            render_image_layer(frame, el, W, H, opacity=opacity, y_offset=y_offset)

    if show_desk_progress:
        for s_start, s_end in scene_windows:
            if s_start <= t < s_end and (s_end - s_start) > 10.0:
                prog = max(0.0, min(1.0, (t - s_start) / (s_end - s_start)))
                draw_scene_progress_bar(frame, W, prog)
                break

    return frame


def download_url_to_temp(url: str, suffix: str = ".bin") -> Optional[str]:
    """Download media URL (audio or video clip) to a temporary file."""
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ByteFYIRenderEngine/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
        if not data or len(data) < 500:
            return None
        tmp_f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_f.write(data)
        tmp_f.close()
        return tmp_f.name
    except Exception as exc:
        print(f"[renderer] Warning: could not download {url}: {exc}")
        return None


def _render_template_modifications_to_mp4(payload: Dict[str, Any], output_mp4_path: str) -> Dict[str, Any]:
    """
    Support multi-clip template modifications payload (used by Daliy-AI-Videos-V3):
    { "template_id": "...", "modifications": { "duration": ..., "video_1.source": ..., "Audio-1.source": ... } }
    """
    t0 = time.time()
    mods = payload.get("modifications") or {}
    W, H, fps = 1080, 1920, 30
    total_duration = float(mods.get("duration") or 60.0)

    clip_specs: List[Tuple[str, float]] = []
    for idx in range(1, 12):
        v_url = mods.get(f"video_{idx}.source") or mods.get(f"Video-{idx}.source")
        v_dur = float(mods.get(f"video_{idx}.duration") or (total_duration / 6.0))
        if v_url:
            clip_specs.append((str(v_url), v_dur))

    audio_url = (
        mods.get("Audio-1.source")
        or mods.get("Audio-TTS.source")
        or mods.get("audio_1.source")
        or mods.get("audio.source")
    )
    audio_path = download_url_to_temp(str(audio_url), suffix=".mp3") if audio_url else None

    image_url = (
        mods.get("Image-2.source")
        or mods.get("Image-1.source")
        or mods.get("image_1.source")
        or mods.get("image.source")
    )

    temp_files: List[str] = []
    segment_files: List[str] = []
    try:
        if not clip_specs and image_url:
            raw_img = download_url_to_temp(str(image_url), suffix="_raw_img.png")
            if raw_img:
                temp_files.append(raw_img)
                seg_out = tempfile.NamedTemporaryFile(delete=False, suffix="_seg_img.mp4").name
                temp_files.append(seg_out)
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    raw_img,
                    "-t",
                    f"{total_duration:.2f}",
                    "-vf",
                    f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "24",
                    "-pix_fmt",
                    "yuv420p",
                    seg_out,
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                segment_files.append(seg_out)

        for i, (v_url, v_dur) in enumerate(clip_specs):
            raw_clip = download_url_to_temp(v_url, suffix=f"_raw_{i}.mp4")
            if not raw_clip:
                continue
            temp_files.append(raw_clip)
            seg_out = tempfile.NamedTemporaryFile(delete=False, suffix=f"_seg_{i}.mp4").name
            temp_files.append(seg_out)
            cmd = [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                raw_clip,
                "-t",
                f"{v_dur:.2f}",
                "-vf",
                f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "26",
                "-maxrate",
                "2000k",
                "-bufsize",
                "4000k",
                "-pix_fmt",
                "yuv420p",
                seg_out,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            segment_files.append(seg_out)

        if not segment_files:
            raise RuntimeError("No valid video clips could be downloaded from modifications")

        concat_list = tempfile.NamedTemporaryFile(delete=False, mode="w", suffix="_concat.txt")
        for sf in segment_files:
            concat_list.write(f"file '{sf}'\n")
        concat_list.close()
        temp_files.append(concat_list.name)

        os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)
        final_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list.name]
        if audio_path and os.path.exists(audio_path):
            temp_files.append(audio_path)
            final_cmd.extend(["-i", audio_path, "-c:a", "aac", "-b:a", "192k", "-shortest"])
        else:
            final_cmd.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-t",
                    f"{total_duration:.2f}",
                ]
            )
        final_cmd.extend(["-c:v", "copy", "-movflags", "+faststart", output_mp4_path])
        subprocess.run(final_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        for tf in temp_files:
            if os.path.exists(tf):
                try:
                    os.unlink(tf)
                except OSError:
                    pass

    return {
        "width": W,
        "height": H,
        "frame_rate": fps,
        "duration": total_duration,
        "file_size": os.path.getsize(output_mp4_path),
        "render_time_seconds": round(time.time() - t0, 2),
    }


def extract_bg_video_frame(video_url: str, W: int, H: int) -> Optional[Image.Image]:
    """Extract a high-resolution frame from a background video element for fast compositing."""
    tmp_vid = download_url_to_temp(video_url, suffix=".mp4")
    if not tmp_vid:
        return None
    tmp_png = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                tmp_vid,
                "-frames:v",
                "1",
                "-vf",
                f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                tmp_png,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        img = Image.open(tmp_png).convert("RGB")
        return img
    except Exception:
        return None
    finally:
        for p in (tmp_vid, tmp_png):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def render_timeline_payload_to_mp4(
    payload: Dict[str, Any],
    output_mp4_path: str,
    save_preview_frames_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Render a declarative JSON timeline payload dictionary into an H.264 + AAC MP4 file.
    Supports:
      - `{ "mode": "keeps_commercial", ... }` (or `source.mode == "keeps_commercial"`)
      - `{ "source": { "elements": [...] } }`
      - `{ "template_id": "...", "modifications": {...} }`
    """
    source_obj = payload.get("source", payload)
    if payload.get("mode") == "keeps_commercial" or (
        isinstance(source_obj, dict) and source_obj.get("mode") == "keeps_commercial"
    ):
        return _render_keeps_commercial_to_mp4(
            source_obj if isinstance(source_obj, dict) and source_obj.get("mode") == "keeps_commercial" else payload,
            output_mp4_path,
        )

    if "modifications" in payload and "source" not in payload:
        return _render_template_modifications_to_mp4(payload, output_mp4_path)

    t0 = time.time()
    source = payload.get("source", payload)
    W = int(source.get("width") or 1080)
    H = int(source.get("height") or 1920)
    fps = int(source.get("frame_rate") or 30)
    elements: List[Dict[str, Any]] = source.get("elements") or []

    max_el_end = 0.0
    for el in elements:
        end_t = float(el.get("time") or 0.0) + float(el.get("duration") or 0.0)
        if end_t > max_el_end:
            max_el_end = end_t
    total_duration = float(source.get("duration") or max_el_end or 60.0)
    total_frames = max(1, int(round(total_duration * fps)))

    show_desk_progress = any("LIVE AI DESK NOTE" in str(el.get("text") or "") for el in elements)

    bg_elements: List[Dict[str, Any]] = []
    fg_elements: List[Dict[str, Any]] = []
    audio_elements: List[Dict[str, Any]] = []
    video_bg_elements: List[Dict[str, Any]] = []

    for el in elements:
        etype = el.get("type")
        if etype == "audio":
            audio_elements.append(el)
            continue
        if etype == "video":
            video_bg_elements.append(el)
            continue
        el_t = float(el.get("time") or 0.0)
        el_d = float(el.get("duration") or total_duration)
        has_anim = bool(el.get("animations"))
        if el_t == 0.0 and abs(el_d - total_duration) < 0.5 and not has_anim:
            bg_elements.append(el)
        else:
            fg_elements.append(el)

    bg_canvas = Image.new("RGB", (W, H), (9, 13, 22))
    if video_bg_elements:
        vid_frame = extract_bg_video_frame(str(video_bg_elements[0].get("source") or ""), W, H)
        if vid_frame is not None:
            bg_canvas = vid_frame

    for el in bg_elements:
        if el.get("type") == "shape":
            render_shape_layer(bg_canvas, el, W, H)
        elif el.get("type") == "text":
            render_text_layer(bg_canvas, el, W, H)
        elif el.get("type") == "image":
            render_image_layer(bg_canvas, el, W, H)

    raw_boundaries = sorted(
        {0.0, round(total_duration, 3)}
        | {
            round(float(e.get("time") or 0.0), 3)
            for e in fg_elements
            if float(e.get("duration") or 0.0) >= 2.0 and float(e.get("time") or 0.0) > 1.0
        }
        | {
            round(float(e.get("time") or 0.0) + float(e.get("duration") or 0.0), 3)
            for e in fg_elements
            if float(e.get("duration") or 0.0) >= 2.0
        }
    )
    boundaries: List[float] = []
    for b in raw_boundaries:
        if not boundaries or (b - boundaries[-1]) >= 0.8:
            boundaries.append(b)
    if boundaries[-1] != round(total_duration, 3):
        boundaries[-1] = round(total_duration, 3)

    scene_windows: List[Tuple[float, float]] = []
    for i in range(len(boundaries) - 1):
        if boundaries[i + 1] - boundaries[i] >= 1.0:
            scene_windows.append((boundaries[i], boundaries[i + 1]))

    steady_scene_cache: Dict[int, Image.Image] = {}
    for s_idx, (s_start, s_end) in enumerate(scene_windows):
        mid_t = s_start + min(1.5, (s_end - s_start) * 0.5)
        steady_scene_cache[s_idx] = render_composite_frame_at_time(
            mid_t, fg_elements, bg_canvas, W, H, scene_windows=[], show_desk_progress=False
        )

    if save_preview_frames_dir:
        os.makedirs(save_preview_frames_dir, exist_ok=True)
        for s_idx, (s_start, s_end) in enumerate(scene_windows):
            preview_img = steady_scene_cache[s_idx].copy()
            if show_desk_progress and (s_end - s_start) > 10.0:
                draw_scene_progress_bar(preview_img, W, 0.5)
            preview_img.save(os.path.join(save_preview_frames_dir, f"scene_{s_idx + 1}.png"))

    audio_paths: List[Tuple[str, float, float]] = []
    for a_el in audio_elements[:2]:
        a_url = a_el.get("source")
        if not a_url:
            continue
        a_path = download_url_to_temp(str(a_url), suffix=".mp3")
        if a_path and os.path.exists(a_path):
            vol = parse_dim(a_el.get("volume"), 1.0, 1.0)
            fade_out = float(a_el.get("audio_fade_out") or 0.8)
            audio_paths.append((a_path, vol, fade_out))

    os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(fps),
        "-i",
        "-",
    ]

    if len(audio_paths) >= 2:
        p0, vol0, fade0 = audio_paths[0]
        p1, vol1, fade1 = audio_paths[1]
        audio_fade_out = max(fade0, fade1, 0.8)
        fade_start = max(0.0, total_duration - audio_fade_out)
        ffmpeg_cmd.extend(["-i", p0, "-stream_loop", "-1", "-i", p1])
        filter_complex = (
            f"[1:a]volume={vol0:.3f},apad=whole_dur={total_duration:.2f}[a0];"
            f"[2:a]volume={vol1:.3f}[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2,"
            f"volume=2.0,afade=t=out:st={fade_start:.2f}:d={audio_fade_out:.2f}[aout]"
        )
        ffmpeg_cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        )
    elif len(audio_paths) == 1:
        p0, vol0, audio_fade_out = audio_paths[0]
        fade_start = max(0.0, total_duration - audio_fade_out)
        ffmpeg_cmd.extend(["-i", p0])
        ffmpeg_cmd.extend(
            [
                "-af",
                f"volume={vol0:.3f},apad=whole_dur={total_duration:.2f},afade=t=out:st={fade_start:.2f}:d={audio_fade_out:.2f}",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        )
    else:
        ffmpeg_cmd.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
            ]
        )

    ffmpeg_cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-maxrate",
            "2500k",
            "-bufsize",
            "5000k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-t",
            f"{total_duration:.2f}",
            output_mp4_path,
        ]
    )

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    assert proc.stdin is not None
    for f_idx in range(total_frames):
        t = f_idx / float(fps)
        active_s_idx = None
        s_start, s_end = 0.0, total_duration
        for idx, (st, en) in enumerate(scene_windows):
            if st <= t < en:
                active_s_idx = idx
                s_start, s_end = st, en
                break

        if active_s_idx is not None and active_s_idx in steady_scene_cache:
            rel_t = t - s_start
            if rel_t < 0.30:
                p = max(0.0, min(1.0, rel_t / 0.30))
                eased = 1.0 - (1.0 - p) ** 3
                frame_rgb = Image.blend(bg_canvas, steady_scene_cache[active_s_idx], eased)
            else:
                frame_rgb = steady_scene_cache[active_s_idx].copy()
            if show_desk_progress and (s_end - s_start) > 10.0:
                prog = max(0.0, min(1.0, rel_t / (s_end - s_start)))
                draw_scene_progress_bar(frame_rgb, W, prog)
            proc.stdin.write(frame_rgb.tobytes())
        else:
            frame_rgb = render_composite_frame_at_time(
                t, fg_elements, bg_canvas, W, H, scene_windows=scene_windows, show_desk_progress=show_desk_progress
            )
            proc.stdin.write(frame_rgb.tobytes())

    proc.stdin.close()
    stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
    ret = proc.wait()

    for a_path, _, _ in audio_paths:
        if a_path and os.path.exists(a_path):
            try:
                os.unlink(a_path)
            except OSError:
                pass

    if ret != 0:
        raise RuntimeError(f"FFmpeg exited with code {ret}: {stderr_out[-600:]}")

    file_size = os.path.getsize(output_mp4_path)
    elapsed = round(time.time() - t0, 2)
    return {
        "width": W,
        "height": H,
        "frame_rate": fps,
        "duration": total_duration,
        "file_size": file_size,
        "render_time_seconds": elapsed,
    }


def _find_chromium_binary() -> Optional[str]:
    """Locate headless Chromium or Chrome binary across Cloud Run (Debian) and macOS dev."""
    import shutil

    candidates = [
        os.environ.get("CHROMIUM_BIN", ""),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        shutil.which("google-chrome") or "",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def render_html_to_png(
    payload: Dict[str, Any],
    output_png_path: str,
) -> Dict[str, Any]:
    """
    Render an HTML/CSS payload (drop-in replacement for HTMLCSSToImg / PDFMunk) into a PNG image.
    Supports fields:
      - `html_content` or `html`
      - `css_content` or `css` (optional)
      - `width` or `viewport_width` (default 1080)
      - `height` or `viewport_height` (default 1920)
    """
    t0 = time.time()
    html_str = str(payload.get("html_content") or payload.get("html") or "").strip()
    css_str = str(payload.get("css_content") or payload.get("css") or "").strip()
    if not html_str:
        raise ValueError("Missing 'html_content' or 'html' in request payload")

    W = int(payload.get("width") or payload.get("viewport_width") or 1080)
    H = int(payload.get("height") or payload.get("viewport_height") or 1920)
    scale = float(payload.get("device_scale_factor") or 1.0)

    # Inject optional css_content and ensure exact viewport sizing
    extra_style = f"<style>html,body{{margin:0;padding:0;}}{css_str}</style>"
    if "</head>" in html_str:
        full_html = html_str.replace("</head>", f"{extra_style}</head>", 1)
    elif "<html" in html_str.lower():
        full_html = f"{extra_style}{html_str}"
    else:
        full_html = (
            f"<!DOCTYPE html><html><head><meta charset='UTF-8'>"
            f"<meta name='viewport' content='width={W},height={H}'>"
            f"{extra_style}</head><body>{html_str}</body></html>"
        )

    os.makedirs(os.path.dirname(os.path.abspath(output_png_path)), exist_ok=True)
    tmp_html = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
    tmp_html.write(full_html)
    tmp_html.close()

    try:
        chrome_bin = _find_chromium_binary()
        if not chrome_bin:
            raise RuntimeError("No Chromium/Chrome binary found for HTML-to-PNG rendering")

        cmd = [
            chrome_bin,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            "--hide-scrollbars",
            f"--force-device-scale-factor={scale}",
            f"--window-size={W},{H}",
            f"--screenshot={output_png_path}",
            f"file://{tmp_html.name}",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
        if res.returncode != 0 or not os.path.exists(output_png_path):
            stderr_msg = res.stderr.decode("utf-8", errors="ignore")[-500:]
            raise RuntimeError(f"Chromium screenshot failed (code {res.returncode}): {stderr_msg}")

        # Verify dimensions and normalize PNG
        with Image.open(output_png_path) as im:
            target_w = int(round(W * scale))
            target_h = int(round(H * scale))
            if im.size != (target_w, target_h):
                im_cropped = im.crop((0, 0, min(im.width, target_w), min(im.height, target_h)))
                if im_cropped.size != (target_w, target_h):
                    im_cropped = im_cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
                im_cropped.save(output_png_path, format="PNG")
    finally:
        if os.path.exists(tmp_html.name):
            try:
                os.unlink(tmp_html.name)
            except OSError:
                pass

    file_size = os.path.getsize(output_png_path)
    elapsed = round(time.time() - t0, 2)
    return {
        "width": W,
        "height": H,
        "file_size": file_size,
        "render_time_seconds": elapsed,
    }


_KEEPS_BGM_CACHE_PATH = "/tmp/keeps_bg_light_commercial.mp3"


def _ensure_keeps_light_commercial_bgm() -> str:
    """Synthesize and cache the airy Apple/Fintech marimba & warm Rhodes commercial bed."""
    if os.path.exists(_KEEPS_BGM_CACHE_PATH) and os.path.getsize(_KEEPS_BGM_CACHE_PATH) > 10000:
        return _KEEPS_BGM_CACHE_PATH

    import struct
    import wave

    sr = 44100
    duration = 45.0
    n_samples = int(sr * duration)
    bpm = 108.0
    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4.0

    chords = [
        [261.63, 329.63, 392.00, 493.88],  # Cmaj7
        [220.00, 261.63, 329.63, 392.00],  # Am7
        [174.61, 220.00, 261.63, 329.63],  # Fmaj7
        [196.00, 246.94, 293.66, 392.00],  # G6
    ]
    pluck_pattern = [0, 2, 1, 3, 2, 3, 1, 2]

    tmp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    try:
        with wave.open(tmp_wav, "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            frames = bytearray()
            for i in range(n_samples):
                t = i / sr
                bar_idx = int(t / bar_sec) % len(chords)
                chord = chords[bar_idx]
                bar_t = t % bar_sec

                pad_env = min(1.0, bar_t / 0.18) * math.exp(-bar_t * 0.45)
                pad_l = 0.0
                pad_r = 0.0
                for idx, freq in enumerate(chord):
                    s = math.sin(2.0 * math.pi * freq * t) + 0.15 * math.sin(2.0 * math.pi * (freq * 2.0) * t)
                    pan = 0.35 + 0.3 * (idx / 3.0)
                    pad_l += s * (1.0 - pan)
                    pad_r += s * pan
                pad_l *= pad_env * 0.14
                pad_r *= pad_env * 0.14

                eighth_sec = beat_sec / 2.0
                step_idx = int(t / eighth_sec) % len(pluck_pattern)
                step_t = t % eighth_sec
                note_freq = chord[pluck_pattern[step_idx]] * 2.0
                pluck_env = math.exp(-step_t * 14.0) * min(1.0, step_t / 0.006)
                pluck_sig = (
                    math.sin(2.0 * math.pi * note_freq * t)
                    + 0.25 * math.sin(2.0 * math.pi * note_freq * 2.0 * t) * math.exp(-step_t * 28.0)
                ) * pluck_env * 0.16

                half_t = t % (beat_sec * 2.0)
                bass_freq = chord[0] * 0.5
                bass_env = math.exp(-half_t * 2.8) * min(1.0, half_t / 0.015)
                bass_sig = math.sin(2.0 * math.pi * bass_freq * t) * bass_env * 0.22

                l_val = max(-0.95, min(0.95, pad_l + pluck_sig * 0.9 + bass_sig))
                r_val = max(-0.95, min(0.95, pad_r + pluck_sig * 1.1 + bass_sig))
                frames.extend(struct.pack("<hh", int(l_val * 32767), int(r_val * 32767)))
            wf.writeframes(frames)

        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_wav, "-c:a", "libmp3lame", "-b:a", "192k", _KEEPS_BGM_CACHE_PATH],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        if os.path.exists(tmp_wav):
            try:
                os.unlink(tmp_wav)
            except OSError:
                pass
    return _KEEPS_BGM_CACHE_PATH


def _render_chrome_card_png(html_body: str, output_png: str, transparent: bool = False) -> None:
    """Render an HTML5/CSS3 1080x1920 commercial card or transparent RGBA overlay via Chromium."""
    chrome_bin = _find_chromium_binary()
    if not chrome_bin:
        raise RuntimeError("Chromium binary not found for commercial card rendering")

    bg_css = "background: transparent;" if transparent else "background: #0B051D;"
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800;900&display=swap');
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  width: 1080px;
  height: 1920px;
  {bg_css}
  font-family: -apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', 'Inter', 'DejaVu Sans', sans-serif;
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
    tmp_html = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
    tmp_html.write(full_html)
    tmp_html.close()
    try:
        cmd = [
            chrome_bin,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--window-size=1080,1920",
        ]
        if transparent:
            cmd.append("--default-background-color=00000000")
        cmd.extend([f"--screenshot={output_png}", f"file://{tmp_html.name}"])
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    finally:
        if os.path.exists(tmp_html.name):
            try:
                os.unlink(tmp_html.name)
            except OSError:
                pass


def _render_keeps_commercial_to_mp4(payload: Dict[str, Any], output_mp4_path: str) -> Dict[str, Any]:
    """
    Render a 6-scene Keeps Commercial Reel (1080x1920, 30fps):
      - Scenes 1 & 2: Live vertical shopper/receipt video clips with floating iOS RGBA overlays
      - Scenes 3–6: Chromium-rendered commercial cards (including populated iPhone 16 Pro Keeps dashboard
        and step-by-step Google Play & Apple App Store search guide)
      - Audio: Broadcast +12 dB vocal presence boost + sidechain-ducked light marimba/Rhodes commercial bed
    """
    import base64

    t0 = time.time()
    W, H, fps = 1080, 1920, 30

    icon_path = os.path.join(os.path.dirname(__file__), "keeps_icon.png")
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as f:
            app_icon_b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    else:
        app_icon_b64 = ""

    cs = payload.get("caseStudy") or {}
    store_name = str(cs.get("store") or "BEST BUY").strip()
    item_name = str(cs.get("item") or "Sony WH-1000XM5 Headphones").strip()
    paid_price = str(cs.get("paidPrice") or "$349.99").strip()
    new_price = str(cs.get("newPrice") or "$279.99").strip()
    refund_amount = str(cs.get("refundAmount") or "$70.00").strip()
    return_days = str(cs.get("returnDays") or "15 Days").strip()
    warranty_period = str(cs.get("warrantyPeriod") or "1 Year").strip()
    alert_headline = str(cs.get("alertHeadline") or f"12 Days Left to Claim at {store_name.title()}").strip()

    raw_durs = payload.get("videoDurations") or [6.0, 6.0, 6.0, 6.5, 6.0, 6.5]
    seg_durations = [max(4.0, float(d)) for d in raw_durs[:6]]
    while len(seg_durations) < 6:
        seg_durations.append(6.0)
    total_dur = float(payload.get("totalAudioDuration") or sum(seg_durations))

    pexels_1_url = str(
        payload.get("pexels_1_url")
        or "https://videos.pexels.com/video-files/9474093/9474093-hd_720_1280_24fps.mp4"
    )
    pexels_2_url = str(
        payload.get("pexels_2_url")
        or "https://videos.pexels.com/video-files/7308301/7308301-hd_720_1280_24fps.mp4"
    )
    audio_url = str(payload.get("audio_url") or "")

    scene1_overlay_html = f"""
<div style="width:1080px;height:1920px;position:relative;background:linear-gradient(180deg, rgba(10,5,28,0.82) 0%, rgba(10,5,28,0.12) 42%, rgba(10,5,28,0.15) 68%, rgba(10,5,28,0.88) 100%);display:flex;flex-direction:column;align-items:center;padding-top:115px;">
  <div style="width:940px;background:rgba(255,255,255,0.96);border-radius:36px;padding:28px 34px;box-shadow:0 24px 60px rgba(0,0,0,0.50);display:flex;align-items:center;gap:26px;">
    <img src="{app_icon_b64}" style="width:96px;height:96px;border-radius:22px;box-shadow:0 8px 20px rgba(110,98,245,0.4);" />
    <div style="flex:1;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:23px;font-weight:800;color:#4F46E5;letter-spacing:0.5px;">KEEPS PRICE WATCH • NOW</span>
        <span style="background:#DCFCE7;color:#059669;font-size:21px;font-weight:900;padding:6px 16px;border-radius:20px;">+{refund_amount} REFUND</span>
      </div>
      <div style="font-size:28px;font-weight:900;color:#0F172A;line-height:1.2;">{store_name.title()} dropped {item_name[:26]} to {new_price}!</div>
      <div style="font-size:22px;font-weight:600;color:#475569;margin-top:4px;">Tap to claim your {refund_amount} cash price-match refund now.</div>
    </div>
  </div>
  <div style="margin-top:54px;text-align:center;padding:0 55px;">
    <div style="display:inline-flex;align-items:center;gap:12px;background:rgba(16,185,129,0.28);border:2px solid #10B981;border-radius:40px;padding:10px 28px;margin-bottom:22px;">
      <span style="font-size:25px;font-weight:800;color:#6EE7B7;letter-spacing:1.2px;">💡 SMART SHOPPER SECRET</span>
    </div>
    <h1 style="font-size:68px;font-weight:900;color:#FFFFFF;line-height:1.10;text-shadow:0 10px 30px rgba(0,0,0,0.85);">
      Bought Something That Went <span style="color:#34D399;">On Sale</span> Days Later?
    </h1>
  </div>
</div>"""

    scene2_overlay_html = f"""
<div style="width:1080px;height:1920px;position:relative;background:linear-gradient(180deg, rgba(10,5,28,0.84) 0%, rgba(10,5,28,0.18) 38%, rgba(10,5,28,0.28) 65%, rgba(10,5,28,0.90) 100%);display:flex;flex-direction:column;align-items:center;padding-top:125px;">
  <div style="display:inline-flex;align-items:center;gap:12px;background:rgba(124,92,255,0.34);border:2px solid #A78BFA;border-radius:40px;padding:10px 30px;margin-bottom:20px;">
    <span style="font-size:25px;font-weight:800;color:#E9D5FF;letter-spacing:1.2px;">⚡ 1-TAP AI RECEIPT SCANNER</span>
  </div>
  <h1 style="font-size:66px;font-weight:900;color:#FFFFFF;line-height:1.10;text-align:center;padding:0 60px;text-shadow:0 10px 30px rgba(0,0,0,0.85);">
    Snap Any Receipt.<br/><span style="color:#34D399;">AI Tracks Every Drop.</span>
  </h1>
  <div style="margin-top:540px;width:920px;background:rgba(19,14,49,0.94);border:2px solid rgba(167,139,250,0.65);border-radius:36px;padding:32px 38px;box-shadow:0 28px 70px rgba(0,0,0,0.65);">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;">
      <div style="display:flex;align-items:center;gap:16px;">
        <img src="{app_icon_b64}" style="width:64px;height:64px;border-radius:16px;" />
        <div>
          <div style="font-size:28px;font-weight:800;color:#FFFFFF;">AI Receipt Extracted in 2.1s</div>
          <div style="font-size:22px;font-weight:600;color:#A78BFA;">{store_name} • {item_name[:26]} ({paid_price})</div>
        </div>
      </div>
      <span style="background:#10B981;color:#022C22;font-size:21px;font-weight:900;padding:10px 22px;border-radius:24px;">✓ TRACKING</span>
    </div>
    <div style="display:flex;gap:18px;">
      <div style="flex:1;background:rgba(255,255,255,0.08);border-radius:22px;padding:16px 18px;text-align:center;">
        <div style="font-size:19px;font-weight:700;color:#94A3B8;">RETURN WINDOW</div>
        <div style="font-size:30px;font-weight:900;color:#FBBF24;margin-top:6px;">⏰ {return_days}</div>
      </div>
      <div style="flex:1;background:rgba(255,255,255,0.08);border-radius:22px;padding:16px 18px;text-align:center;">
        <div style="font-size:19px;font-weight:700;color:#94A3B8;">WARRANTY VAULT</div>
        <div style="font-size:30px;font-weight:900;color:#38BDF8;margin-top:6px;">🛡️ {warranty_period}</div>
      </div>
      <div style="flex:1;background:rgba(16,185,129,0.20);border:1.5px solid #10B981;border-radius:22px;padding:16px 18px;text-align:center;">
        <div style="font-size:19px;font-weight:700;color:#A7F3D0;">PRICE WATCH</div>
        <div style="font-size:30px;font-weight:900;color:#34D399;margin-top:6px;">⚡ 24/7 ON</div>
      </div>
    </div>
  </div>
</div>"""

    scene3_html = """
<div style="width:1080px;height:1920px;background:radial-gradient(circle at 50% 42%, #2E1760 0%, #160A36 52%, #0B051D 100%);display:flex;flex-direction:column;align-items:center;padding-top:230px;position:relative;">
  <div style="position:absolute;top:400px;width:720px;height:720px;background:radial-gradient(circle, rgba(16,185,129,0.22) 0%, transparent 70%);z-index:0;"></div>
  <div style="position:relative;z-index:2;background:rgba(16,185,129,0.16);border:2px solid #10B981;border-radius:50px;padding:14px 38px;margin-bottom:34px;">
    <span style="font-size:27px;font-weight:800;color:#6EE7B7;letter-spacing:1.5px;">💡 SECRET SHOPPING HACK</span>
  </div>
  <h1 style="position:relative;z-index:2;font-size:78px;font-weight:900;color:#FFFFFF;text-align:center;line-height:1.12;padding:0 70px;">
    Stores Everywhere<br/>Owe You<br/><span style="color:#2DD4BF;">Price-Drop Refunds!</span>
  </h1>
  <p style="position:relative;z-index:2;font-size:34px;font-weight:500;color:#CBD5E1;text-align:center;line-height:1.42;padding:0 95px;margin-top:30px;">
    Did you know retailers will refund you the cash difference if an item goes on sale after you buy it?
  </p>
  <div style="position:relative;z-index:2;margin-top:48px;width:900px;background:rgba(255,255,255,0.06);border:1.5px solid rgba(255,255,255,0.16);border-radius:36px;padding:40px 42px;display:flex;flex-direction:column;align-items:center;">
    <div style="font-size:34px;font-weight:800;color:#FFFFFF;margin-bottom:28px;">🏢 Works For ANY Store You Shop At</div>
    <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:18px;">
      <div style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.18);border-radius:40px;padding:16px 32px;font-size:28px;font-weight:700;color:#F8FAFC;">💻 Best Buy &amp; Tech</div>
      <div style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.18);border-radius:40px;padding:16px 32px;font-size:28px;font-weight:700;color:#F8FAFC;">🛒 Costco &amp; Target</div>
      <div style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.18);border-radius:40px;padding:16px 32px;font-size:28px;font-weight:700;color:#F8FAFC;">🛋️ Home Depot &amp; Lowe's</div>
      <div style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.18);border-radius:40px;padding:16px 32px;font-size:28px;font-weight:700;color:#F8FAFC;">🛍️ Amazon &amp; Walmart</div>
      <div style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.18);border-radius:40px;padding:16px 32px;font-size:28px;font-weight:700;color:#F8FAFC;">📦 Any Paper or Digital Receipt</div>
    </div>
    <div style="margin-top:32px;width:100%;background:rgba(244,63,94,0.18);border:1.5px solid rgba(244,63,94,0.45);border-radius:22px;padding:18px 28px;text-align:center;font-size:26px;font-weight:700;color:#FDA4AF;">
      ⚠️ The Catch: You must claim before your store return window closes!
    </div>
  </div>
</div>"""

    scene4_html = f"""
<div style="width:1080px;height:1920px;background:radial-gradient(circle at 50% 48%, #341B70 0%, #170B3B 55%, #0B051D 100%);display:flex;flex-direction:column;align-items:center;padding-top:95px;position:relative;">
  <div style="background:rgba(124,92,255,0.22);border:2px solid #8B5CF6;border-radius:50px;padding:12px 36px;margin-bottom:20px;">
    <span style="font-size:26px;font-weight:800;color:#DDD6FE;letter-spacing:1.4px;">⚡ AUTO PRICE WATCH &amp; ALERTS</span>
  </div>
  <h1 style="font-size:72px;font-weight:900;color:#FFFFFF;text-align:center;line-height:1.10;">
    Snap Any Receipt.<br/><span style="color:#A78BFA;">Keeps Does The Rest.</span>
  </h1>
  <div style="margin-top:30px;width:620px;height:1100px;background:#F8FAFC;border-radius:64px;border:14px solid #1E1B2E;box-shadow:0 35px 90px rgba(0,0,0,0.65), 0 0 0 3px rgba(167,139,250,0.35);overflow:hidden;display:flex;flex-direction:column;position:relative;">
    <div style="background:linear-gradient(135deg, #7C6FF9 0%, #6355E8 100%);padding:22px 28px 24px 28px;color:#FFFFFF;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;">
        <span style="font-size:22px;font-weight:700;">11:21</span>
        <div style="width:150px;height:36px;background:#09090B;border-radius:20px;"></div>
        <span style="font-size:20px;font-weight:700;">5G 100%</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div style="font-size:36px;font-weight:900;letter-spacing:-0.5px;">☑️ Keeps</div>
          <div style="display:flex;align-items:center;gap:10px;margin-top:4px;">
            <span style="font-size:20px;opacity:0.9;">Dashboard</span>
            <span style="background:rgba(255,255,255,0.22);font-size:15px;font-weight:800;padding:4px 12px;border-radius:12px;">🟢 CLOUD SYNC ACTIVE</span>
          </div>
        </div>
        <div style="display:flex;gap:12px;">
          <div style="width:46px;height:46px;border-radius:23px;background:rgba(255,255,255,0.2);display:flex;align-items:center;justify-content:center;font-size:22px;">🔔</div>
          <div style="width:46px;height:46px;border-radius:23px;background:rgba(255,255,255,0.2);display:flex;align-items:center;justify-content:center;font-size:22px;">⚙️</div>
        </div>
      </div>
    </div>
    <div style="padding:18px 24px 0 24px;display:flex;flex-direction:column;gap:12px;">
      <div style="background:#FFFFFF;border-radius:22px;padding:15px 20px;box-shadow:0 8px 24px rgba(15,23,42,0.09);border:1.5px solid #D1FAE5;display:flex;justify-content:space-between;align-items:center;">
        <div style="display:flex;align-items:center;gap:14px;">
          <span style="font-size:30px;">💰</span>
          <div>
            <div style="font-size:20px;font-weight:800;color:#0F172A;">{store_name.title()} • {item_name[:22]}</div>
            <div style="font-size:16px;font-weight:600;color:#059669;">Price dropped {paid_price} → {new_price} (Claim Refund)</div>
          </div>
        </div>
        <span style="background:#10B981;color:#FFFFFF;font-size:17px;font-weight:800;padding:6px 14px;border-radius:12px;">+{refund_amount}</span>
      </div>
      <div style="background:#FFFFFF;border-radius:22px;padding:15px 20px;box-shadow:0 8px 24px rgba(15,23,42,0.09);border:1.5px solid #FEE2E2;display:flex;justify-content:space-between;align-items:center;">
        <div style="display:flex;align-items:center;gap:14px;">
          <span style="font-size:30px;">🔔</span>
          <div>
            <div style="font-size:20px;font-weight:800;color:#0F172A;">Target • Dyson V15 Vacuum</div>
            <div style="font-size:16px;font-weight:600;color:#EF4444;">Return window closing soon</div>
          </div>
        </div>
        <span style="background:#FEF2F2;color:#DC2626;font-size:16px;font-weight:800;padding:6px 12px;border-radius:12px;">3 DAYS LEFT</span>
      </div>
    </div>
    <div style="padding:18px 24px;display:grid;grid-template-columns:1fr 1fr;gap:16px;flex:1;">
      <div style="background:linear-gradient(135deg, #3B82F6 0%, #2563EB 100%);border-radius:28px;padding:22px;color:#FFFFFF;display:flex;flex-direction:column;justify-content:space-between;">
        <div style="width:46px;height:46px;border-radius:23px;background:rgba(255,255,255,0.22);display:flex;align-items:center;justify-content:center;font-size:24px;">🧾</div>
        <div>
          <div style="font-size:52px;font-weight:900;line-height:1;">47</div>
          <div style="font-size:20px;font-weight:600;opacity:0.92;margin-top:6px;">Total Receipts</div>
        </div>
      </div>
      <div style="background:linear-gradient(135deg, #10B981 0%, #059669 100%);border-radius:28px;padding:22px;color:#FFFFFF;display:flex;flex-direction:column;justify-content:space-between;">
        <div style="width:46px;height:46px;border-radius:23px;background:rgba(255,255,255,0.22);display:flex;align-items:center;justify-content:center;font-size:24px;">💵</div>
        <div>
          <div style="font-size:50px;font-weight:900;line-height:1;">$412</div>
          <div style="font-size:20px;font-weight:600;opacity:0.92;margin-top:6px;">Returnable Value</div>
        </div>
      </div>
      <div style="background:linear-gradient(135deg, #F59E0B 0%, #D97706 100%);border-radius:28px;padding:22px;color:#FFFFFF;display:flex;flex-direction:column;justify-content:space-between;">
        <div style="width:46px;height:46px;border-radius:23px;background:rgba(255,255,255,0.22);display:flex;align-items:center;justify-content:center;font-size:24px;">⏰</div>
        <div>
          <div style="font-size:52px;font-weight:900;line-height:1;">3</div>
          <div style="font-size:20px;font-weight:600;opacity:0.92;margin-top:6px;">Expiring Soon</div>
        </div>
      </div>
      <div style="background:linear-gradient(135deg, #8B5CF6 0%, #6D28D9 100%);border-radius:28px;padding:22px;color:#FFFFFF;display:flex;flex-direction:column;justify-content:space-between;">
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="font-size:22px;">📊</span>
          <span style="font-size:21px;font-weight:800;">Top Stores</span>
        </div>
        <div style="font-size:18px;font-weight:700;line-height:1.45;">
          • Best Buy ($349)<br/>
          • Costco ($284)<br/>
          • Target ($165)
        </div>
      </div>
    </div>
    <div style="margin:0 24px 18px 24px;background:linear-gradient(90deg, #10B981 0%, #059669 100%);border-radius:24px;padding:16px 22px;color:#FFFFFF;display:flex;align-items:center;gap:16px;box-shadow:0 10px 25px rgba(16,185,129,0.35);">
      <span style="font-size:30px;">🔍</span>
      <div>
        <div style="font-size:21px;font-weight:900;">Active 24/7 Price Monitor</div>
        <div style="font-size:16px;font-weight:600;opacity:0.95;">Scans prices across retailers every 4 hours</div>
      </div>
    </div>
  </div>
  <div style="display:flex;gap:18px;margin-top:24px;">
    <div style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.2);border-radius:30px;padding:12px 26px;font-size:23px;font-weight:700;color:#FFFFFF;">🏢 Any Store Receipt</div>
    <div style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.2);border-radius:30px;padding:12px 26px;font-size:23px;font-weight:700;color:#FFFFFF;">⏰ Return Countdowns</div>
    <div style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.2);border-radius:30px;padding:12px 26px;font-size:23px;font-weight:700;color:#FFFFFF;">💵 Auto Refunds</div>
  </div>
</div>"""

    scene5_html = f"""
<div style="width:1080px;height:1920px;background:radial-gradient(circle at 50% 48%, #1E3A4C 0%, #190D3A 52%, #0B051D 100%);display:flex;flex-direction:column;align-items:center;padding-top:300px;position:relative;">
  <div style="position:absolute;top:520px;width:850px;height:600px;background:radial-gradient(circle, rgba(16,185,129,0.28) 0%, transparent 70%);z-index:0;"></div>
  <div style="position:relative;z-index:2;background:rgba(244,63,94,0.2);border:2px solid #F43F5E;border-radius:50px;padding:14px 38px;margin-bottom:32px;">
    <span style="font-size:28px;font-weight:800;color:#FDA4AF;letter-spacing:1.5px;">🚨 PRICE DROP DETECTED</span>
  </div>
  <h1 style="position:relative;z-index:2;font-size:84px;font-weight:900;color:#FFFFFF;text-align:center;line-height:1.10;margin-bottom:50px;">
    Claim Your <span style="color:#2DD4BF;">Cash<br/>Refund!</span>
  </h1>
  <div style="position:relative;z-index:2;width:920px;background:#FFFFFF;border-radius:42px;padding:48px 52px;box-shadow:0 30px 80px rgba(0,0,0,0.55), 0 0 80px rgba(16,185,129,0.25);">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:26px;">
      <span style="font-size:28px;font-weight:800;color:#334155;">{store_name} • Price Match Alert</span>
      <span style="background:#DCFCE7;color:#059669;font-size:22px;font-weight:900;padding:10px 24px;border-radius:24px;letter-spacing:0.8px;">PRICE DROPPED</span>
    </div>
    <div style="font-size:42px;font-weight:900;color:#0F172A;margin-bottom:24px;">
      {item_name}
    </div>
    <div style="display:flex;align-items:baseline;gap:28px;margin-bottom:38px;">
      <span style="font-size:38px;font-weight:600;color:#94A3B8;text-decoration:line-through;">You Paid: {paid_price}</span>
      <span style="font-size:56px;font-weight:900;color:#059669;">Now: {new_price}</span>
    </div>
    <div style="width:100%;background:linear-gradient(90deg, #10B981 0%, #059669 100%);border-radius:28px;padding:28px;text-align:center;font-size:36px;font-weight:900;color:#FFFFFF;box-shadow:0 12px 30px rgba(16,185,129,0.35);">
      💰 You Can Claim a {refund_amount} Refund!
    </div>
  </div>
  <div style="position:relative;z-index:2;margin-top:40px;font-size:32px;font-weight:700;color:#F8FAFC;display:flex;align-items:center;gap:14px;">
    <span>⏰ {alert_headline}</span>
  </div>
</div>"""

    scene6_html = f"""
<div style="width:1080px;height:1920px;background:radial-gradient(circle at 50% 42%, #3B1F82 0%, #1C0D42 55%, #0D0622 100%);display:flex;flex-direction:column;align-items:center;padding-top:115px;position:relative;">
  <div style="position:absolute;top:300px;width:760px;height:760px;background:radial-gradient(circle, rgba(139,92,246,0.38) 0%, transparent 70%);z-index:0;"></div>
  <div style="position:relative;z-index:2;background:rgba(16,185,129,0.20);border:2px solid #10B981;border-radius:50px;padding:12px 38px;margin-bottom:22px;">
    <span style="font-size:26px;font-weight:800;color:#6EE7B7;letter-spacing:1.4px;">📲 HOW TO DOWNLOAD IN 5 SECONDS</span>
  </div>
  <h1 style="position:relative;z-index:2;font-size:68px;font-weight:900;color:#FFFFFF;text-align:center;line-height:1.10;margin-bottom:36px;">
    Search on <span style="color:#38BDF8;">Google Play</span><br/>or <span style="color:#A78BFA;">Apple App Store</span>
  </h1>
  <div style="position:relative;z-index:2;width:920px;background:rgba(255,255,255,0.08);border:2px solid rgba(167,139,250,0.45);border-radius:36px;padding:28px 36px;margin-bottom:28px;box-shadow:0 20px 50px rgba(0,0,0,0.35);">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
      <span style="background:#7C6FF9;color:#FFFFFF;font-size:21px;font-weight:900;padding:7px 20px;border-radius:20px;letter-spacing:0.8px;">STEP 1 • TYPE IN SEARCH BAR</span>
      <span style="font-size:22px;font-weight:700;color:#CBD5E1;">iOS App Store &amp; Google Play</span>
    </div>
    <div style="width:100%;background:#FFFFFF;border-radius:26px;padding:20px 28px;display:flex;align-items:center;justify-content:space-between;box-shadow:0 12px 30px rgba(0,0,0,0.35);border:3px solid #38BDF8;">
      <div style="display:flex;align-items:center;gap:18px;">
        <span style="font-size:36px;">🔍</span>
        <span style="font-size:38px;font-weight:900;color:#0F172A;letter-spacing:-0.3px;">Keeps Receipt Scanner</span>
        <span style="display:inline-block;width:4px;height:42px;background:#2563EB;border-radius:2px;"></span>
      </div>
      <div style="background:#2563EB;color:#FFFFFF;font-size:24px;font-weight:800;padding:12px 28px;border-radius:18px;">Search</div>
    </div>
  </div>
  <div style="position:relative;z-index:2;width:920px;background:rgba(255,255,255,0.08);border:2px solid rgba(16,185,129,0.55);border-radius:36px;padding:28px 36px;margin-bottom:34px;box-shadow:0 24px 60px rgba(0,0,0,0.45);">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
      <span style="background:#10B981;color:#022C22;font-size:21px;font-weight:900;padding:7px 20px;border-radius:20px;letter-spacing:0.8px;">STEP 2 • LOOK FOR THIS ICON &amp; TAP INSTALL</span>
      <span style="font-size:22px;font-weight:800;color:#6EE7B7;">✓ Official App</span>
    </div>
    <div style="width:100%;background:#FFFFFF;border-radius:28px;padding:26px 30px;display:flex;align-items:center;gap:26px;box-shadow:0 16px 40px rgba(0,0,0,0.35);">
      <img src="{app_icon_b64}" style="width:142px;height:142px;border-radius:32px;box-shadow:0 12px 28px rgba(124,111,249,0.45);flex-shrink:0;" />
      <div style="flex:1;">
        <div style="font-size:32px;font-weight:900;color:#0F172A;line-height:1.15;">Keeps: Receipt Scanner Tracker</div>
        <div style="font-size:22px;font-weight:700;color:#6366F1;margin-top:6px;">Auto Price Watch • Return &amp; Warranty Alerts</div>
        <div style="display:flex;align-items:center;gap:14px;margin-top:10px;">
          <span style="font-size:24px;color:#F59E0B;font-weight:900;">★★★★★ 4.9</span>
          <span style="font-size:20px;font-weight:700;color:#64748B;">• Free Download</span>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px;align-items:center;">
        <div style="background:#007AFF;color:#FFFFFF;font-size:26px;font-weight:900;padding:12px 34px;border-radius:26px;width:155px;text-align:center;box-shadow:0 6px 16px rgba(0,122,255,0.35);">GET</div>
        <div style="background:#059669;color:#FFFFFF;font-size:24px;font-weight:900;padding:12px 26px;border-radius:26px;width:155px;text-align:center;box-shadow:0 6px 16px rgba(5,150,105,0.35);">Install</div>
      </div>
    </div>
  </div>
  <div style="position:relative;z-index:2;display:flex;gap:26px;width:920px;margin-bottom:32px;">
    <div style="flex:1;background:#FFFFFF;border-radius:28px;padding:20px 28px;display:flex;align-items:center;gap:20px;box-shadow:0 16px 40px rgba(0,0,0,0.4);">
      <div style="width:60px;height:60px;border-radius:16px;background:linear-gradient(135deg,#38BDF8,#2563EB);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="white"><path d="M5 3l14 9-14 9V3z"/></svg>
      </div>
      <div>
        <div style="font-size:17px;font-weight:800;color:#64748B;letter-spacing:1px;">GET IT ON</div>
        <div style="font-size:35px;font-weight:900;color:#0F172A;line-height:1.08;">Google Play</div>
      </div>
    </div>
    <div style="flex:1;background:#FFFFFF;border-radius:28px;padding:20px 28px;display:flex;align-items:center;gap:20px;box-shadow:0 16px 40px rgba(0,0,0,0.4);">
      <div style="width:60px;height:60px;border-radius:16px;background:#7C6FF9;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="white"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M15.97 6.33c.64-.78 1.08-1.86.96-2.94-.93.04-2.06.62-2.72 1.4-.58.68-1.1 1.79-.96 2.84 1.04.08 2.08-.52 2.72-1.3z"/></svg>
      </div>
      <div>
        <div style="font-size:17px;font-weight:800;color:#64748B;letter-spacing:1px;">DOWNLOAD ON THE</div>
        <div style="font-size:35px;font-weight:900;color:#0F172A;line-height:1.08;">App Store</div>
      </div>
    </div>
  </div>
  <div style="position:relative;z-index:2;background:rgba(16,185,129,0.24);border:2px solid #10B981;border-radius:40px;padding:18px 46px;font-size:26px;font-weight:800;color:#ECFDF5;">
    🔗 Or Tap the Direct Link in Bio / Description to Download!
  </div>
</div>"""

    work_dir = tempfile.mkdtemp(prefix="keeps_comm_")
    try:
        s1_ov = os.path.join(work_dir, "s1_ov.png")
        s2_ov = os.path.join(work_dir, "s2_ov.png")
        s3_png = os.path.join(work_dir, "s3.png")
        s4_png = os.path.join(work_dir, "s4.png")
        s5_png = os.path.join(work_dir, "s5.png")
        s6_png = os.path.join(work_dir, "s6.png")

        _render_chrome_card_png(scene1_overlay_html, s1_ov, transparent=True)
        _render_chrome_card_png(scene2_overlay_html, s2_ov, transparent=True)
        _render_chrome_card_png(scene3_html, s3_png, transparent=False)
        _render_chrome_card_png(scene4_html, s4_png, transparent=False)
        _render_chrome_card_png(scene5_html, s5_png, transparent=False)
        _render_chrome_card_png(scene6_html, s6_png, transparent=False)

        seg_files: List[str] = []
        for idx, (vid_url, ov_png, dur) in enumerate(
            [(pexels_1_url, s1_ov, seg_durations[0]), (pexels_2_url, s2_ov, seg_durations[1])],
            start=1,
        ):
            out_seg = os.path.join(work_dir, f"seg_{idx}.mp4")
            dl_vid = download_url_to_temp(vid_url, suffix=f"_p{idx}.mp4")
            if dl_vid and os.path.exists(dl_vid):
                try:
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-stream_loop",
                            "-1",
                            "-i",
                            dl_vid,
                            "-i",
                            ov_png,
                            "-t",
                            f"{dur:.2f}",
                            "-filter_complex",
                            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v0];"
                            "[v0][1:v]overlay=0:0:format=auto,format=yuv420p[vout]",
                            "-map",
                            "[vout]",
                            "-an",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "veryfast",
                            "-crf",
                            "22",
                            out_seg,
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                finally:
                    try:
                        os.unlink(dl_vid)
                    except OSError:
                        pass
            else:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-loop",
                        "1",
                        "-i",
                        ov_png,
                        "-t",
                        f"{dur:.2f}",
                        "-vf",
                        "fps=30,format=yuv420p",
                        "-an",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "22",
                        out_seg,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            seg_files.append(out_seg)

        for idx, (card_png, dur) in enumerate(
            [
                (s3_png, seg_durations[2]),
                (s4_png, seg_durations[3]),
                (s5_png, seg_durations[4]),
                (s6_png, seg_durations[5]),
            ],
            start=3,
        ):
            out_seg = os.path.join(work_dir, f"seg_{idx}.mp4")
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    card_png,
                    "-t",
                    f"{dur:.2f}",
                    "-vf",
                    "fps=30,fade=t=in:st=0:d=0.35,format=yuv420p",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "22",
                    out_seg,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            seg_files.append(out_seg)

        concat_txt = os.path.join(work_dir, "concat.txt")
        with open(concat_txt, "w") as f:
            for sf in seg_files:
                f.write(f"file '{sf}'\n")

        os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)
        bgm_path = _ensure_keeps_light_commercial_bgm()
        vo_path = download_url_to_temp(audio_url, suffix="_vo.mp3") if audio_url else None

        try:
            if vo_path and os.path.exists(vo_path):
                fade_start = max(0.0, total_dur - 1.5)
                cmd_final = [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    concat_txt,
                    "-i",
                    vo_path,
                    "-stream_loop",
                    "-1",
                    "-i",
                    bgm_path,
                    "-filter_complex",
                    f"[1:a]highpass=f=85,equalizer=f=2800:t=q:w=1.2:g=3.5,"
                    f"acompressor=threshold=-24dB:ratio=3.5:attack=4:release=60:makeup=7dB,"
                    f"volume=2.4,alimiter=limit=0.96,apad=whole_dur={total_dur:.2f},asplit=2[vo_main][vo_sc];"
                    f"[2:a]highpass=f=110,lowpass=f=2200,equalizer=f=1400:t=q:w=1.0:g=-8,"
                    f"volume=0.055,afade=t=in:st=0:d=0.8,afade=t=out:st={fade_start:.2f}:d=1.50[bgm_pre];"
                    f"[bgm_pre][vo_sc]sidechaincompress=threshold=0.015:ratio=6:attack=10:release=250[bgm_ducked];"
                    f"[vo_main][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
                    f"alimiter=limit=0.97[aout]",
                    "-map",
                    "0:v",
                    "-map",
                    "[aout]",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-t",
                    f"{total_dur:.2f}",
                    "-movflags",
                    "+faststart",
                    output_mp4_path,
                ]
            else:
                cmd_final = [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    concat_txt,
                    "-stream_loop",
                    "-1",
                    "-i",
                    bgm_path,
                    "-map",
                    "0:v",
                    "-map",
                    "1:a",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-t",
                    f"{total_dur:.2f}",
                    "-movflags",
                    "+faststart",
                    output_mp4_path,
                ]
            subprocess.run(cmd_final, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            if vo_path and os.path.exists(vo_path):
                try:
                    os.unlink(vo_path)
                except OSError:
                    pass
    finally:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)

    return {
        "width": W,
        "height": H,
        "frame_rate": fps,
        "duration": total_dur,
        "file_size": os.path.getsize(output_mp4_path),
        "render_time_seconds": round(time.time() - t0, 2),
    }


