"""
Tests para element_detector.py — detección de bubbles WA por color.
Correr desde poc/whatsapp-vision/:
    .venv/bin/python -m pytest tests/ -v
"""
import numpy as np
import pytest
from PIL import Image

from element_detector import _build_masks, _merge_overlapping, detect_bubbles


# ─── _merge_overlapping ──────────────────────────────────────────────────────

def test_merge_fuses_same_type_close_gap():
    bubbles = [
        {"x": 10, "y": 0,  "w": 100, "h": 50, "type": "me"},
        {"x": 10, "y": 55, "w": 100, "h": 50, "type": "me"},  # gap = 5 ≤ 8
    ]
    result = _merge_overlapping(bubbles, overlap_gap=8)
    assert len(result) == 1
    assert result[0]["y"] == 0
    assert result[0]["h"] == 105  # y=0 → y1=105


def test_merge_keeps_different_types_regardless_of_gap():
    bubbles = [
        {"x": 10, "y": 0,  "w": 100, "h": 50, "type": "me"},
        {"x": 10, "y": 55, "w": 100, "h": 50, "type": "other"},  # gap=5 but distinct type
    ]
    result = _merge_overlapping(bubbles, overlap_gap=8)
    assert len(result) == 2


def test_merge_no_merge_large_gap():
    bubbles = [
        {"x": 10, "y": 0,  "w": 100, "h": 50, "type": "me"},
        {"x": 10, "y": 70, "w": 100, "h": 50, "type": "me"},  # gap = 20 > 8
    ]
    result = _merge_overlapping(bubbles, overlap_gap=8)
    assert len(result) == 2


def test_merge_expands_bounding_box_correctly():
    bubbles = [
        {"x": 50, "y": 0,  "w": 200, "h": 40, "type": "other"},
        {"x": 60, "y": 45, "w": 180, "h": 40, "type": "other"},  # gap=5, wider x
    ]
    result = _merge_overlapping(bubbles, overlap_gap=8)
    assert len(result) == 1
    assert result[0]["x"] == 50   # min x
    assert result[0]["w"] == 200  # max x1 = 60+180=240, x0=50 → w=190... wait
    # x1_a = 50+200=250, x1_b = 60+180=240 → max=250 → w=250-50=200
    assert result[0]["w"] == 200
    assert result[0]["h"] == 85   # y=0, y1 = 45+40=85


def test_merge_empty_list():
    assert _merge_overlapping([]) == []


def test_merge_single_bubble():
    b = {"x": 0, "y": 0, "w": 100, "h": 50, "type": "me"}
    assert _merge_overlapping([b]) == [b]


# ─── _build_masks ────────────────────────────────────────────────────────────

def test_build_masks_green_pixel():
    # G−R=120>15, G−B=120>15, G=220>200 → mask_me=1, mask_other=0
    arr = np.array([[[100, 220, 100]]], dtype=np.uint8)
    mask_me, mask_other = _build_masks(arr)
    assert mask_me[0, 0] == 1
    assert mask_other[0, 0] == 0


def test_build_masks_white_pixel():
    arr = np.array([[[255, 255, 255]]], dtype=np.uint8)
    mask_me, mask_other = _build_masks(arr)
    assert mask_me[0, 0] == 0
    assert mask_other[0, 0] == 1


def test_build_masks_beige_background():
    # Fondo del chat WA: (243, 238, 231) → ninguna máscara activa
    arr = np.array([[[243, 238, 231]]], dtype=np.uint8)
    mask_me, mask_other = _build_masks(arr)
    assert mask_me[0, 0] == 0
    assert mask_other[0, 0] == 0


def test_build_masks_wa_green_exact():
    # Color exacto de bubbles "me" en WA Web
    arr = np.array([[[217, 253, 211]]], dtype=np.uint8)
    mask_me, mask_other = _build_masks(arr)
    assert mask_me[0, 0] == 1


# ─── detect_bubbles ──────────────────────────────────────────────────────────

def _make_chat_img(w=400, h=300):
    return Image.new("RGB", (w, h), (243, 238, 231))


def _paint_rect(img, x0, y0, x1, y1, color):
    pixels = img.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            pixels[x, y] = color
    return img


WA_GREEN = (217, 253, 211)
WA_WHITE = (255, 255, 255)


def test_detect_single_me_bubble():
    img = _make_chat_img()
    _paint_rect(img, 290, 50, 380, 120, WA_GREEN)  # 90×70 px

    bubbles = detect_bubbles(img, footer_px=0)
    me = [b for b in bubbles if b["type"] == "me"]
    assert len(me) == 1
    assert me[0]["x"] == 290
    assert me[0]["y"] == 50
    assert me[0]["w"] == 90
    assert me[0]["h"] == 70


def test_detect_single_other_bubble():
    img = _make_chat_img()
    _paint_rect(img, 10, 30, 160, 100, WA_WHITE)  # 150×70 px

    bubbles = detect_bubbles(img, footer_px=0)
    other = [b for b in bubbles if b["type"] == "other"]
    assert len(other) == 1
    assert other[0]["x"] == 10
    assert other[0]["y"] == 30
    assert other[0]["w"] == 150
    assert other[0]["h"] == 70


def test_detect_filters_small_components():
    # Rectángulo 20×20: demasiado pequeño (h<30, w<50) → filtrado
    img = _make_chat_img()
    _paint_rect(img, 10, 10, 30, 30, WA_GREEN)

    bubbles = detect_bubbles(img, footer_px=0)
    assert len(bubbles) == 0


def test_detect_footer_excluded():
    # Bubble en zona del footer → no debe detectarse
    img = _make_chat_img(h=300)
    # Pintamos en los últimos 60px (dentro del footer_px=70)
    _paint_rect(img, 10, 250, 200, 295, WA_WHITE)

    bubbles = detect_bubbles(img, footer_px=70)
    assert len(bubbles) == 0


def test_detect_multiple_bubbles_ordered_by_y():
    img = _make_chat_img(h=400)
    _paint_rect(img, 10,  20, 160, 80,  WA_WHITE)   # other, y=20
    _paint_rect(img, 200, 120, 380, 200, WA_GREEN)  # me, y=120
    _paint_rect(img, 10,  220, 160, 290, WA_WHITE)   # other, y=220

    bubbles = detect_bubbles(img, footer_px=0)
    assert len(bubbles) == 3
    ys = [b["y"] for b in bubbles]
    assert ys == sorted(ys)
