# POC: WhatsApp Vision Scraper

Vision-based WhatsApp chat analysis — screenshot → crop → OCR → parse.
No DOM selectors. Robust to UI changes.

## Stack
- **Browser**: Playwright (Python, Chromium)
- **Image processing**: Pillow
- **OCR**: macOS Vision framework (Swift, no external API)
- **Python**: 3.12, venv at `.venv/`

## Scripts
| Script | Purpose |
|--------|---------|
| `01_crop_test.py` | Crop sidebar out, isolate chat panel |
| `02_ocr_test.py` | Tiled OCR with 2.5x upscale on reference image |
| `03_message_parser.py` | Parse OCR blocks → structured messages |
| `04_full_pipeline.py` | **Full pipeline** — run this |
| `ocr_vision.swift` | macOS Vision OCR helper (called by Python) |

## Run
```bash
.venv/bin/python 04_full_pipeline.py assets/reference_chat.png
```

## POC Results (reference image)
- **35 messages** detected
- **Other person**: 18 messages / **Me**: 17 messages
- **File attachments**: 7 (5 Excel + 2 Screen Recordings)
- **Audio messages**: 0 (see Issues)

## Known Issues & Next Steps

### Issue 1: Audio messages not counted
OCR garbles duration strings:
- "0:38" → "058", "0 38", "0-38"
- RE_AUDIO_LOOSE pattern added but OCR produces garbled formats
- **Fix**: Broaden audio detection, or detect by waveform visual (needs vision model)

### Issue 2: Excel file names garbled
OCR misreads `.xlsx` extension:
- "ARBOL GENERAL.xlsx" → "ARDOL GENERAL aisx"
- "PEDIDO PERFILES.xlsx" → "PEDIDO PERFILES SÍSE"
- **Fix**: Post-process filenames, normalize garbled extensions
- Extra: First Excel file size line "XISE - 1115" doesn't match kB/MB → not detected as attachment

### Issue 3: Duplicate/fragmented messages
Tile overlap (50px) sometimes produces duplicate text blocks.
Current dedup catches most cases but not all.
**Fix**: Increase dedup window, use text similarity not just prefix.

### Issue 4: Message fragmentation at tile boundaries
A long message that spans a tile boundary gets split into 2 messages.
**Fix**: Increase tile overlap to 100px.

## Vision Control Architecture (next phase)
Instead of DOM selectors (fragile to WA updates), control the browser by:
1. Take full screenshot
2. Run Vision OCR to locate UI elements by text
3. Click by coordinates (not CSS selectors)
4. Scroll by pixel delta
5. Repeat until full conversation extracted

This makes the scraper independent of WA Web's HTML structure.

## Multi-agent development model (planned)
- **Opus**: Planning, architecture decisions, final review
- **Sonnet**: User communication, code review every N iterations
- **Haiku**: Implementation — file reads, MCP results, heavy lifting
