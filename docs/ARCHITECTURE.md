# ByteFYI Render Engine Architecture (`app/renderer.py`)

## 1. Declarative Timeline Coordinate & Layout Model

The renderer implements a declarative JSON timeline specification so existing n8n template builder nodes require **zero code changes**:

- **Canvas Dimensions**: Defaults to `width = 1080`, `height = 1920`, `frame_rate = 30`.
- **Center-Anchored Bounding Boxes**:
  - Every element (`shape`, `text`, `image`) defines `(x, y)` and `(width, height)` in either `px` or `%` of the canvas.
  - Unless `x_anchor` / `y_anchor` is explicitly provided, bounding boxes are centered at `(x, y)`:
    - `box_left = x - width * 0.5`
    - `box_top = y - height * 0.5`
- **Typography & Alignment (`render_text_layer`)**:
  - Horizontal text alignment inside `[box_left, box_left + width]` prioritizes `text_alignment` (`"left"`, `"center"`, `"right"`) and falls back to `x_alignment` (`"0%"` → left, `"50%"` → center, `"100%"` → right).
  - Vertical alignment inside `[box_top, box_top + height]` uses `y_alignment` (`"0%"` → top, `"50%"` → middle, `"100%"` → bottom).
  - Multi-line paragraphs are word-wrapped automatically to fit inside `width` while honoring `line_height` percentages (e.g., `"128%"`, `"135%"`).

---

## 2. Broadcast Visual Features

1. **True Alpha-Blended RGB Compositing**:
   - All drawing operations execute with `ImageDraw.Draw(rgb_canvas, "RGBA")` over an `RGB` base buffer so translucent elements (`rgba(148, 163, 184, 0.08)` terminal grid lines, `rgba(250, 204, 21, 0.18)` VWAP luminescence, and `rgba(6, 78, 59, 0.85)` trade badges) blend accurately over `#090D16`.
2. **2x Supersampled Rounded Rectangles**:
   - Every rounded card and candlestick body is rasterized on an isolated `2x`-resolution `RGBA` patch and downsampled with `Image.Resampling.LANCZOS` for razor-sharp corners and `2px` borders.
3. **Custom Broadcast Vector Icons (`draw_vector_icon`)**:
   - Leading indicators (`⚡`, `🟢`, `🎙️`) are intercepted and drawn as multi-layered anti-aliased vector polygons/arcs so Linux containers never render `.notdef` boxes or washed-out monochrome glyphs.
4. **Live 30fps Audio-Synced Progress Bar (`draw_scene_progress_bar`)**:
   - During each stock setup scene (`duration > 10s`), a sleek cyan progress bar (`#38BDF8`) animates smoothly across the bottom of the AI Desk Note card (`y = 1716px`).

---

## 3. Scene-Interval Caching for Fast Encoding

A 93.36-second video at `30 fps` contains `2,801` frames (`1080×1920`). Rendering all `354` elements from scratch on every frame would require `~990,000` layer operations.

Instead, `render_timeline_payload_to_mp4` performs three optimizations:
1. **Static Background Pre-Bake (`bg_canvas`)**:
   - All full-duration background shapes and grid lines (`time == 0`, `duration == total_duration`) are composited **once** before the frame loop begins.
2. **Scene Steady-State Caching (`steady_scene_cache`)**:
   - Time boundaries are extracted from the foreground elements (e.g., Intro `0–5.88s`, Setup 1 `5.88–26.76s`, Setup 2 `26.76–47.67s`, Setup 3 `47.67–68.21s`, Setup 4 `68.21–88.00s`, Outro `88.00–93.36s`).
   - Each scene's steady-state frame is rendered **once** and cached in memory.
3. **Hybrid Frame Loop**:
   - During the first `0.30s` (`9` frames) of each scene, fast `Image.blend(bg_canvas, steady_frame, eased)` interpolation runs with cubic ease-out (`1 - (1 - p)^3`).
   - For the remaining `~98%` of frames, the renderer copies the cached steady-state `RGB` frame (`<0.2 ms`), draws the live `30fps` progress bar, and pipes raw `rgb24` bytes directly into `ffmpeg` stdin.
