#!/usr/bin/env python3
"""
POC Full Pipeline: Screenshot → Crop → OCR → Parse → Report
Usage: python 04_full_pipeline.py <screenshot.png>
       python 04_full_pipeline.py  # uses reference image

This is the complete proof-of-concept for vision-based WhatsApp chat analysis.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Import our modules
sys.path.insert(0, str(Path(__file__).parent))
from importlib import import_module

SWIFT_OCR = Path(__file__).parent / "ocr_vision.swift"
ASSETS = Path(__file__).parent / "assets"

from element_detector import detect_bubbles  # noqa: E402 (imported after path setup)

# ─── Step 1: Crop ────────────────────────────────────────────────────────────

def find_sidebar_end(img: Image.Image) -> int:
    """Detect where the WA Web sidebar ends.
    TODO: replace with OCR-based detection — run OCR on the top strip,
    find the contact name text, use its x as the chat panel start.
    That approach is robust to any WA design change.
    For now: hardcoded based on measured pixel boundary at 1280px viewport."""
    w, _ = img.size
    # Measured: sidebar ends at ~580px for 1280px wide viewport
    # Scale proportionally for other widths
    return int(w * (580 / 1280))


def crop_chat_panel(img_path: Path) -> Path:
    img = Image.open(img_path)
    w, h = img.size
    sidebar_end = find_sidebar_end(img)
    header_px = 60
    chat = img.crop((sidebar_end, header_px, w, h))
    out = ASSETS / (img_path.stem + "_cropped.png")
    chat.save(out)
    print(f"  → sidebar detected at x={sidebar_end}px ({sidebar_end/w:.1%} of width)")
    return out

# ─── Step 2: OCR with tiling ─────────────────────────────────────────────────

def run_ocr(img_path: Path) -> list[dict]:
    r = subprocess.run(["swift", str(SWIFT_OCR), str(img_path)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"OCR error: {r.stderr}", file=sys.stderr)
        return []
    return json.loads(r.stdout)

def ocr_tiled(img_path: Path, tile_h=500, overlap=50, scale=2.5) -> list[dict]:
    img = Image.open(img_path)
    w, h = img.size
    all_blocks = []
    y = 0
    while y < h:
        y_end = min(y + tile_h, h)
        tile = img.crop((0, y, w, y_end))
        tile_up = tile.resize((int(w * scale), int((y_end - y) * scale)), Image.LANCZOS)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = Path(f.name)
        tile_up.save(tmp)
        blocks = run_ocr(tmp)
        tmp.unlink()
        tile_frac_start = y / h
        tile_frac_h = (y_end - y) / h
        for b in blocks:
            b["y"] = tile_frac_start + b["y"] * tile_frac_h
            b["h"] = b["h"] * tile_frac_h
        all_blocks.extend(blocks)
        y += tile_h - overlap

    # Dedup
    seen, deduped = set(), []
    for b in sorted(all_blocks, key=lambda x: (round(x["y"], 3), x["text"][:10])):
        key = (b["text"][:20], round(b["y"] * h / 10) * 10)
        if key not in seen:
            seen.add(key)
            deduped.append(b)
    return deduped

# ─── Step 3: Parse ───────────────────────────────────────────────────────────
# (inline from 03_message_parser.py to keep pipeline self-contained)

import re
from dataclasses import dataclass, field, asdict
from typing import Literal

RE_TIME = re.compile(r'\d{1,2}:\d{2}\s*(a|p)\.?\s*m\.?', re.I)
# Timestamp at END of a block (handles OCR-merged text+timestamp, e.g. "Que haces capo!!? 7:29 p. m.")
RE_TIME_END = re.compile(r'\d{1,2}:\d{2}\s*(a|p)\.?\s*m\.?\s*[JVjv/✓✔✗]*\s*$', re.I)
RE_CORE_TIME = re.compile(r'(\d{1,2}:\d{2})\s*(a|p)', re.I)
RE_DURATION = re.compile(r'^\d+:\d{2}$')
RE_AUDIO_LOOSE = re.compile(r'^0[\s\-\.]?\d{2}$')  # "0 38", "058", "0-38"
RE_FILE_EXT = re.compile(r'\.(xlsx?|docx?|pdf|csv|pptx?|txt|zip|rar|mov|mp4|png|jpg|jpeg)\b', re.I)
RE_SCREEN_REC = re.compile(r'Screen Recording', re.I)
RE_SIZE = re.compile(r'\d+[\.,]?\d*\s*(kB|MB|GB|k8|M8)\b', re.I)
# Audio duration: M:SS not followed by a/p (am/pm) — distinguishes "1:11" (audio) from "3:55 p. m." (timestamp)
RE_AUDIO_DURATION = re.compile(r'\b\d{1,2}:\d{2}\b(?!\s*[ap])', re.I)
RE_NOISE = re.compile(r'^(\+|\s*Escribe un mensaje.*|.*filtrados.*|.*encriptados.*|\d{3,}/\d{3,})', re.I)


@dataclass
class Attachment:
    name: str
    size: str = ""
    kind: str = "file"


@dataclass
class Message:
    sender: Literal["other", "me", "unknown"]
    text: str
    time: str = ""
    attachments: list = field(default_factory=list)
    y_pos: float = 0.0

    def is_empty(self):
        return not self.text.strip() and not self.attachments


def classify_x(x, w):
    # WA "me" bubbles always end near the right edge of the panel.
    # WA "other" bubbles always start near the left edge.
    # Using the right/left edge is more robust than center for short lines.
    right_edge = x + w
    if right_edge > 0.75:
        return "me"
    if x < 0.15:
        return "other"
    return "me" if (x + w / 2) > 0.50 else "other"


def is_noise(text):
    t = text.strip()
    if not t or len(t) < 2:
        return True
    if RE_NOISE.match(t):
        return True
    if len(t) <= 4 and not re.search(r'[a-záéíóú]', t, re.I):
        # Duraciones de audio ("0:38", "1:23") son válidas aunque sean cortas
        if not RE_DURATION.match(t) and not RE_AUDIO_LOOSE.match(t):
            return True
    if re.match(r'^[А-ЯЁа-яё\s\-]+$', t):
        return True
    return False


def tag_blocks(blocks):
    n = len(blocks)
    for i, b in enumerate(blocks):
        b["role"] = "text"
        t = b["text"].strip()
        if RE_DURATION.match(t) or RE_AUDIO_LOOSE.match(t):
            b["role"] = "audio_duration"
        elif RE_TIME.search(t) and len(t) < 25:
            b["role"] = "timestamp"
        elif RE_SCREEN_REC.search(t):
            b["role"] = "filename"
        elif RE_FILE_EXT.search(t):
            b["role"] = "filename"
        elif RE_SIZE.search(t):
            b["role"] = "filesize"
            if i > 0 and blocks[i-1]["role"] == "text":
                blocks[i-1]["role"] = "filename"
        elif i + 1 < n and RE_SIZE.search(blocks[i+1]["text"]):
            b["role"] = "filename"
    return blocks


def group_into_messages(blocks, y_gap=0.020):
    clean = [b for b in blocks if not is_noise(b["text"])]
    clean.sort(key=lambda b: b["y"])
    tag_blocks(clean)

    deduped = []
    for b in clean:
        if deduped and b["text"].strip()[:15] == deduped[-1]["text"].strip()[:15]:
            if abs(b["y"] - deduped[-1]["y"]) < 0.006:
                continue
        deduped.append(b)

    messages, current, current_side, last_y, pending_filename = [], None, "", -1, ""

    for b in deduped:
        side = classify_x(b["x"], b["w"])
        y, role, t = b["y"], b["role"], b["text"].strip()

        # Side change alone is not enough — a short line in a "me" bubble can
        # have x+w/2 < 0.5 and look like "other". Only split on side change when
        # there's also a meaningful y gap (≥ 0.006 = ~24px at 3940px height).
        gap = abs(y - last_y)
        side_changed = side != current_side and role not in ("timestamp", "filesize")
        start_new = current is None or gap > y_gap or (side_changed and gap >= 0.003)

        if start_new:
            if current and not current.is_empty():
                messages.append(current)
            current = Message(sender=side, text="", y_pos=y)
            current_side = side
            pending_filename = ""

        if role == "audio_duration":
            current.attachments.append(Attachment(name=t, kind="audio"))
        elif role == "filename":
            pending_filename = t
        elif role == "filesize":
            kind = "screen_recording" if "Screen Recording" in pending_filename else "file"
            current.attachments.append(Attachment(name=pending_filename or "?", size=t, kind=kind))
            pending_filename = ""
        elif role == "timestamp":
            current.time = t
        else:
            if pending_filename:
                kind = "screen_recording" if "Screen Recording" in pending_filename else "file"
                current.attachments.append(Attachment(name=pending_filename, kind=kind))
                pending_filename = ""
            current.text = (current.text + " " + t).strip() if current.text else t

        last_y = y

    if current and not current.is_empty():
        messages.append(current)
    return messages


def _core_time(text: str) -> str | None:
    """Extract normalized HH:MM+a/p from a text block (e.g. '7:29p')."""
    m = RE_CORE_TIME.search(text)
    return (m.group(1) + m.group(2).lower()) if m else None


def _extract_timestamp(raw_blocks: list[dict]) -> str | None:
    """Extract the message timestamp string from per-bubble OCR blocks.

    Tries standalone blocks first (short, only a time), then embedded
    (timestamp at end of a longer text line).
    """
    for b in raw_blocks:
        t = b["text"].strip()
        if len(t) < 25 and RE_TIME.search(t):
            m = RE_TIME.search(t)
            return t[m.start():m.end()].strip()
    for b in raw_blocks:
        t = b["text"].strip()
        if RE_TIME_END.search(t):
            m = RE_TIME.search(t)
            if m:
                return t[m.start():m.end()].strip()
    return None


def _split_bubble_by_timestamps(bubble: dict, blocks: list[dict], img_h: int) -> list[dict]:
    """Split a merged color blob into individual message boxes.

    Two categories of timestamp indicators are used:
    1. Standalone blocks (role=='timestamp'): short blocks like '7:29 p. m.'
    2. Embedded blocks: longer OCR blocks where text+timestamp were merged on one
       line, e.g. 'Que haces capo??!! 7:29 p. m.' — detected via RE_TIME_END.

    To avoid double-counting (when both exist for the same message), embedded blocks
    are skipped when a standalone of the same core time exists within 80px below.
    """
    b_y0_frac = bubble["y"] / img_h
    b_y1_frac = (bubble["y"] + bubble["h"]) / img_h

    inner = [b for b in blocks if b_y0_frac <= b["y"] <= b_y1_frac]

    standalone = [b for b in inner if b.get("role") == "timestamp"]
    embedded = [
        b for b in inner
        if b.get("role") != "timestamp" and RE_TIME_END.search(b["text"].strip())
    ]

    def has_same_time_standalone_below(emb: dict) -> bool:
        emb_core = _core_time(emb["text"])
        emb_bot = (emb["y"] + emb.get("h", 0.008)) * img_h
        for s in standalone:
            s_top = s["y"] * img_h
            if 0 < s_top - emb_bot <= 80 and _core_time(s["text"]) == emb_core:
                return True
        return False

    clean_embedded = [e for e in embedded if not has_same_time_standalone_below(e)]

    all_cut_blocks = standalone + clean_embedded

    if len(all_cut_blocks) <= 1:
        return [bubble]

    cut_points: list[int] = []
    for b in all_cut_blocks:
        y_bot = int((b["y"] + b.get("h", 0.008)) * img_h) + 6
        y_bot = min(y_bot, bubble["y"] + bubble["h"])
        cut_points.append(y_bot)
    cut_points = sorted(set(cut_points))

    sub_bubbles: list[dict] = []
    y_start_px = bubble["y"]
    for cut in cut_points:
        h_slice = cut - y_start_px
        if h_slice > 10:
            sub_bubbles.append({
                "x": bubble["x"],
                "y": y_start_px,
                "w": bubble["w"],
                "h": h_slice,
                "type": bubble["type"],
            })
        y_start_px = cut

    remaining = (bubble["y"] + bubble["h"]) - y_start_px
    if sub_bubbles and remaining > 0:
        sub_bubbles[-1]["h"] += remaining

    return sub_bubbles if sub_bubbles else [bubble]


def draw_message_boxes(cropped_path: Path, messages, blocks) -> Path:
    """Draw bounding boxes around each detected bubble using color-based detection.

    Color coding: green → "me" bubble, blue → "other" bubble.

    Consecutive messages from the same person are split using OCR timestamps:
    each message ends at the bottom of its timestamp, so N timestamps in one
    color blob → N separate boxes.
    """
    img = Image.open(cropped_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    PAD = 4

    bubbles = detect_bubbles(img, footer_px=70)

    # Split merged blobs into individual message boxes via timestamp positions
    split: list[dict] = []
    for bubble in bubbles:
        split.extend(_split_bubble_by_timestamps(bubble, blocks, h))

    for i, bubble in enumerate(split):
        x0 = max(0,     bubble["x"] - PAD)
        y0 = max(0,     bubble["y"] - PAD)
        x1 = min(w - 1, bubble["x"] + bubble["w"] + PAD)
        y1 = min(h - 1, bubble["y"] + bubble["h"] + PAD)

        color = (0, 180, 80) if bubble["type"] == "me" else (0, 120, 220)
        label = f"#{i+1} {bubble['type']}"

        draw.rectangle([(x0, y0), (x1, y1)], outline=color, width=2)
        draw.text((x0 + 2, y0 + 2), label, fill=color)

    out = ASSETS / (cropped_path.stem.replace("_cropped", "") + "_annotated.png")
    img.save(out)
    return out, split


def _is_waveform_garbage(text: str) -> bool:
    """True if the block looks like OCR noise from an audio waveform."""
    if len(text) < 5:
        return False
    noise = sum(1 for c in text if c in '|•01-[]lL ')
    return noise / len(text) > 0.45


def classify_msg_type(text: str, raw_blocks: list[dict]) -> str:
    """Classify a bubble as: text | audio | file | media.

    Priority: file > audio > media > text.
    All signals are derived from OCR output — no hardcoded colors.
    """
    if RE_SIZE.search(text) or RE_FILE_EXT.search(text) or RE_SCREEN_REC.search(text):
        return "file"
    has_duration = bool(RE_AUDIO_DURATION.search(text))
    has_waveform = any(_is_waveform_garbage(b["text"]) for b in raw_blocks)
    if has_duration or has_waveform:
        return "audio"
    if not text.strip():
        return "media"
    return "text"


def extract_bubble_texts(cropped_path: Path, bubbles: list[dict]) -> list[dict]:
    """OCR each individual bubble crop and return per-message structured data.

    Running OCR on the full image and then assigning blocks by Y position is fragile.
    Cropping first and OCR-ing each bubble independently gives a 1:1 mapping between
    image region and message text, with no positional guesswork.

    Scale: at least 3x; bumped to 5x for very short bubbles (<40px) to keep text legible.
    """
    img = Image.open(cropped_path)
    img_w, img_h = img.size
    results: list[dict] = []

    for i, bubble in enumerate(bubbles):
        x0 = max(0, bubble["x"])
        y0 = max(0, bubble["y"])
        x1 = min(img_w, bubble["x"] + bubble["w"])
        y1 = min(img_h, bubble["y"] + bubble["h"])

        crop = img.crop((x0, y0, x1, y1))
        cw, ch = crop.size

        scale = 5.0 if ch < 40 else 3.0
        crop_up = crop.resize((int(cw * scale), int(ch * scale)), Image.LANCZOS)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = Path(f.name)
        crop_up.save(tmp)
        raw_blocks = run_ocr(tmp)
        tmp.unlink()

        text = " ".join(b["text"].strip() for b in raw_blocks if b["text"].strip())
        timestamp = _extract_timestamp(raw_blocks)
        msg_type = classify_msg_type(text, raw_blocks)

        # Click point in cropped-panel coordinates (no sidebar offset yet)
        if msg_type == "audio":
            rx, ry = _find_play_button(crop, bubble["type"])
            click_point = {"x": x0 + rx, "y": y0 + ry}
        elif msg_type == "file":
            rx, ry = _find_file_click(crop)
            click_point = {"x": x0 + rx, "y": y0 + ry}
        else:
            click_point = None

        results.append({
            "id": len(bubbles) - i,   # 1 = newest (bottom), N = oldest (top)
            "sender": bubble["type"],
            "msg_type": msg_type,
            "timestamp": timestamp,
            "click_point": click_point,
            "bbox": {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0},
            "text": text,
            "raw_blocks": raw_blocks,
        })

    missing = [r["id"] for r in results if r["timestamp"] is None]
    if missing:
        print(f"  ⚠  sin timestamp: ids {missing}")
    return results


def _find_play_button(crop: Image.Image, sender: str) -> tuple[int, int]:
    """Locate the ▶ play button in an audio bubble crop.

    Layout differs by sender:
    - "other": [▶ button][waveform]  → ▶ is at far left, ~25px wide; search first 12.5%
    - "me":    [avatar][▶ button][waveform]  → avatar ≈ bubble height wide, skip then search

    Uses min-x of dark pixels (not median) for "other" so waveform bars don't push it right.
    """
    arr = np.array(crop.convert("L"))
    h, w = arr.shape

    if sender == "me":
        # Avatar is roughly square (diameter ≈ bubble height). Skip it.
        x_start = int(h * 0.75)
        x_end   = min(w, x_start + int(h * 0.70))
    else:
        # ▶ is at the very left edge of the bubble; waveform bars start ~30px in.
        # Narrow window to avoid including waveform dark pixels.
        x_start = 0
        x_end   = max(1, w // 8)

    region = arr[:, x_start:x_end]
    lo, hi = int(region.min()), int(region.max())
    if hi == lo:
        return (x_start + x_end) // 2, h // 2
    dark_thresh = lo + (hi - lo) * 0.30
    mask = region < dark_thresh
    if not mask.any():
        return (x_start + x_end) // 2, h // 2
    ys, xs = np.where(mask)
    if sender == "other":
        # Use min-x: ▶ is the leftmost dark region; median would average in waveform bars
        return x_start + int(xs.min()), int(np.median(ys))
    return x_start + int(np.median(xs)), int(np.median(ys))


def _find_file_click(crop: Image.Image) -> tuple[int, int]:
    """Locate the click point for a file attachment.

    The file box is a sub-region with a uniform color noticeably different
    from the bubble background. We find the centroid of all pixels that
    deviate significantly from the bubble's median color.
    """
    arr = np.array(crop.convert("RGB")).astype(np.float32)
    h, w = arr.shape[:2]
    bg = np.median(arr.reshape(-1, 3), axis=0)
    diff = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    thresh = diff.mean() + diff.std() * 0.8
    mask = diff > thresh
    if not mask.any():
        return w // 2, h // 2
    ys, xs = np.where(mask)
    return int(xs.mean()), int(ys.mean())


def draw_click_crosshairs(annotated_path: Path, bubble_data: list[dict]) -> Path:
    """Draw click points on the annotated image, type-aware.

    - text  → no cross (skip)
    - audio → cross on ▶ play button (left third, darkest region)
    - file  → cross on file-box center (inner region differing from bg)
    - media → cross at center (fallback)

    Color: red. Numbers match bubble id.
    """
    cropped_path = Path(str(annotated_path).replace("_annotated", "_cropped"))
    panel = Image.open(cropped_path)
    img = Image.open(annotated_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    ARM = 10

    for b in bubble_data:
        if b["msg_type"] == "text":
            continue

        x0 = b["bbox"]["x"]
        y0 = b["bbox"]["y"]
        bw = b["bbox"]["w"]
        bh = b["bbox"]["h"]
        crop = panel.crop((x0, y0, x0 + bw, y0 + bh))

        if b["msg_type"] == "audio":
            rx, ry = _find_play_button(crop, b["sender"])
        elif b["msg_type"] == "file":
            rx, ry = _find_file_click(crop)
        else:
            rx, ry = bw // 2, bh // 2

        cx, cy = x0 + rx, y0 + ry
        draw.line([(cx - ARM, cy), (cx + ARM, cy)], fill=(255, 0, 0), width=2)
        draw.line([(cx, cy - ARM), (cx, cy + ARM)], fill=(255, 0, 0), width=2)
        draw.text((cx + ARM + 2, cy - 6), str(b["id"]), fill=(255, 0, 0))

    out = annotated_path.parent / annotated_path.name.replace("_annotated", "_click_points")
    img.save(out)
    return out


def count_stats(messages):
    stats = {"total": len(messages), "other": 0, "me": 0, "audio": 0, "files": []}
    for m in messages:
        stats[m.sender] = stats.get(m.sender, 0) + 1
        for att in m.attachments:
            if att.kind == "audio":
                stats["audio"] += 1
            else:
                stats["files"].append({"name": att.name, "size": att.size, "kind": att.kind})
    return stats


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_pipeline(img_path: Path):
    print(f"\n{'='*60}")
    print(f"WHATSAPP VISION PIPELINE")
    print(f"Input: {img_path.name}")
    print(f"{'='*60}")

    print("\n[1/3] Cropping chat panel...")
    cropped = crop_chat_panel(img_path)
    print(f"  → {cropped.name} ({Image.open(cropped).size})")

    print("\n[2/3] Running OCR (tiled, 2.5x upscale)...")
    blocks = ocr_tiled(cropped)
    print(f"  → {len(blocks)} text blocks extracted")

    print("\n[3/3] Parsing messages...")
    messages = group_into_messages(blocks)
    stats = count_stats(messages)

    print("\n[+] Drawing message bounding boxes (color-based detector)...")
    annotated, bubbles = draw_message_boxes(cropped, messages, blocks)
    print(f"  → {annotated.name}")
    print(f"  → detector found {len(bubbles)} bubbles  "
          f"(me={sum(1 for b in bubbles if b['type']=='me')}  "
          f"other={sum(1 for b in bubbles if b['type']=='other')})")

    print("\n[4/4] OCR per bubble crop...")
    bubble_data = extract_bubble_texts(cropped, bubbles)
    out_bubbles = ASSETS / (img_path.stem + "_bubbles.json")
    with open(out_bubbles, "w") as f:
        json.dump(bubble_data, f, indent=2, ensure_ascii=False)
    print(f"  → {out_bubbles.name}  ({len(bubble_data)} mensajes)")

    click_img = draw_click_crosshairs(annotated, bubble_data)
    print(f"  → {click_img.name}  (debug: centros de click)")

    print(f"\n{'─'*60}")
    print("BUBBLES (text per message)")
    print(f"{'─'*60}")
    for b in bubble_data:
        preview = b["text"][:80].replace("\n", " ")
        print(f"  #{b['id']:2d} [{b['sender']:5s}]  {preview}")

    return stats, messages


if __name__ == "__main__":
    img = Path(sys.argv[1]) if len(sys.argv) > 1 else ASSETS / "reference_chat.png"
    stats, messages = run_pipeline(img)
