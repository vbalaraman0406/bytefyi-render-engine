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

    audio_url = mods.get("Audio-1.source") or mods.get("audio_1.source") or mods.get("audio.source")
    audio_path = download_url_to_temp(str(audio_url), suffix=".mp3") if audio_url else None

    temp_files: List[str] = []
    segment_files: List[str] = []
    try:
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
    Supports both `{ "source": { "elements": [...] } }` and `{ "template_id": "...", "modifications": {...} }`.
    """
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

    boundaries = sorted(
        {0.0, round(total_duration, 3)}
        | {
            round(float(e.get("time") or 0.0), 3)
            for e in fg_elements
            if float(e.get("duration") or 0.0) > 2.0 and float(e.get("time") or 0.0) > 1.0
        }
        | {
            round(float(e.get("time") or 0.0) + float(e.get("duration") or 0.0), 3)
            for e in fg_elements
            if float(e.get("duration") or 0.0) > 2.0
        }
    )
    scene_windows: List[Tuple[float, float]] = []
    for i in range(len(boundaries) - 1):
        if boundaries[i + 1] - boundaries[i] > 1.0:
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

    audio_path = None
    audio_fade_out = 0.5
    if audio_elements:
        audio_url = audio_elements[0].get("source")
        audio_fade_out = float(audio_elements[0].get("audio_fade_out") or 0.5)
        audio_path = download_url_to_temp(str(audio_url), suffix=".mp3")

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

    if audio_path and os.path.exists(audio_path):
        ffmpeg_cmd.extend(["-i", audio_path])
        fade_start = max(0.0, total_duration - audio_fade_out)
        ffmpeg_cmd.extend(
            [
                "-af",
                f"afade=t=out:st={fade_start:.2f}:d={audio_fade_out:.2f}",
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
            "ultrafast",
            "-crf",
            "20",
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

    if audio_path and os.path.exists(audio_path):
        try:
            os.unlink(audio_path)
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
