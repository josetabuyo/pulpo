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
RE_DURATION = re.compile(r'^\d+:\d{2}$')
RE_AUDIO_LOOSE = re.compile(r'^0[\s\-\.]?\d{2}$')  # "0 38", "058", "0-38"
RE_FILE_EXT = re.compile(r'\.(xlsx?|docx?|pdf|csv|pptx?|txt|zip|rar|mov|mp4|png|jpg|jpeg)\b', re.I)
RE_SCREEN_REC = re.compile(r'Screen Recording', re.I)
RE_SIZE = re.compile(r'\d+[\.,]?\d*\s*(kB|MB|GB|k8|M8)\b', re.I)
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


def draw_message_boxes(cropped_path: Path, messages, blocks) -> Path:
    """Draw bounding boxes around each detected bubble using color-based detection.

    Boxes come from element_detector.detect_bubbles() — one box per bubble regardless
    of how many OCR paragraphs it contains. Color coding:
      green  → "me" bubble
      blue   → "other" bubble

    NOTE: media bubbles (photo/video thumbnails) are NOT color-uniform and will be
    missed by the detector. File-attachment bubbles (xlsx, mov, etc.) are white
    rectangles and will be detected as "other" or merged with their container.
    This is a known limitation of the color-based approach.
    """
    img = Image.open(cropped_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    PAD = 4  # pixels of extra padding around each box

    # Detect bubbles by color (replaces OCR-based message grouping for drawing)
    bubbles = detect_bubbles(img, footer_px=70)

    for i, bubble in enumerate(bubbles):
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
    return out, bubbles


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

    print(f"\n{'─'*60}")
    print("RESULTS")
    print(f"{'─'*60}")
    print(f"Messages found:    {stats['total']}")
    print(f"  Other person:    {stats.get('other', 0)}")
    print(f"  Me:              {stats.get('me', 0)}")
    print(f"Audio messages:    {stats['audio']}")
    print(f"File attachments:  {len(stats['files'])}")
    for f in stats["files"]:
        print(f"  [{f['kind']}] {f['name']}  {f['size']}")

    out = ASSETS / (img_path.stem + "_pipeline_result.json")
    with open(out, "w") as f:
        json.dump({"stats": stats, "messages": [asdict(m) for m in messages]}, f, indent=2, ensure_ascii=False)
    print(f"\nFull results: {out}")
    return stats, messages


if __name__ == "__main__":
    img = Path(sys.argv[1]) if len(sys.argv) > 1 else ASSETS / "reference_chat.png"
    stats, messages = run_pipeline(img)
