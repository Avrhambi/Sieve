# TASK-04 Public API

## Module: `src.visual.ocr_pipeline`

### `extract_text(image_path: str | Path) -> str`

| | |
|---|---|
| **Purpose** | Extracts all readable text from an image file using RapidOCR (PaddleOCR PP-StructureV3). |
| **Returns** | Multi-line string — one detected text region per line. Empty string if nothing detected or on error. |
| **Raises** | Never raises; failures are logged as warnings and return `""`. |

**Invariants:**
- CPU-only; no VRAM-heavy model (`clip`, `llava`, `transformers`) is ever loaded.
- RapidOCR engine is lazy-initialised on first call (~30MB, loaded once per process).
- Reads `config.thresholds.VRAM_THRESHOLD_MB` via `load_config()` from `src.main`; used for logging context only (CPU path has no VRAM constraint).

---

## Module: `src.visual.toaster`

### `to_toast(raw_text: str) -> str`

| | |
|---|---|
| **Purpose** | Converts OCR-extracted text into a compact bulleted Structural Toast. |
| **Returns** | Newline-joined bullet string (`• line\n• line\n…`) or `"(no content)"` when input is blank/noise-only. |
| **Raises** | Never raises. |

**Output format example:**
```
• def calculate_total(items: list[Item]) -> float:
• Returns sum of item prices after discount
• raise ValueError if items is empty
```

**Invariants:**
- Pure transformation — no I/O, no network calls, no model imports.
- Deduplicates lines case-sensitively, preserving first-occurrence order.
- Strips horizontal rules, blank lines, and lone box-drawing characters.

---

## Config Keys Read

| Key | Module | Usage |
|---|---|---|
| `config.thresholds.VRAM_THRESHOLD_MB` | `ocr_pipeline` | Logged for context; CPU path is always used regardless of value. |
