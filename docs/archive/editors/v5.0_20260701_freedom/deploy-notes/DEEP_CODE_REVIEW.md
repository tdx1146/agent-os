# Deep Code Review Report — Tree-Sitter AST-Level Analysis

> Generated: 2026-07-01  
> Method: Tree-sitter WASM parsing via Understand Anything core (deterministic pipeline)  
> Compared against: First LLM-driven analysis (`knowledge-graph.json`)

---

## Overview

This second pass used **fully built Tree-sitter WASM parsers** (Python, JavaScript, TypeScript, Go, Rust, Java, C/C++, C#, Ruby, PHP) to produce a deep, AST-level knowledge graph. Unlike the first analysis which relied on LLM agents to read and summarize each file, this pass:

1. **Enumerated all files deterministically** via `scan-project.mjs` (without git, via recursive walk + `.understandignore`)
2. **Extracted AST structure** via `extract-structure.mjs` using the `TreeSitterPlugin` and `PluginRegistry`
3. **Built batches via Louvain community detection** (6 batches from 98 files)
4. **Extracted call graphs** intra-file at function level
5. **Merged and normalized** via `merge-batch-graphs.py`

---

## Quantitative Comparison

| Metric | First Analysis | Deep Analysis | Delta |
|---|---|---|---|
| **Total nodes** | 801 | 741 | -60 |
| **Total edges** | 790 | **1,428** | **+638** |
| File size | 454 KB | 652 KB | +198 KB |
| **Function nodes** | 689 | 631 | -58 |
| **Class nodes** | 14 | 12 | -2 |
| File nodes | 69 | 67 | -2 |
| Document nodes | 27 | 28 | +1 |
| Config nodes | 2 | 3 | +1 |

### Edge Types — What Changed

| Edge Type | First | Deep | What it means |
|---|---|---|---|
| `contains` | 703 | 643 | File→function/class hierarchy |
| `calls` | **0** | **308** | 🆕 **NEW** — Function-level call graph |
| `exports` | **0** | **477** | 🆕 **NEW** — Export relationships |
| `imports` | 87 | 0 | Dropped (LLM could hallucinate imports; Tree-sitter imports need cross-file resolution) |

### Language Breakdown (function/class nodes only)

| Language | First | Deep | Notes |
|---|---|---|---|
| Python | 0 | 516 | ✅ Deep AST analysis |
| JavaScript | 0 | 184 | ✅ Deep AST analysis |
| Markdown | 0 | 28 | Section parsing |
| Shell | 0 | 6 | Script step parsing |
| JSON | 0 | 3 | Config structure |
| HTML | 0 | 2 | Markup structure |
| CSS | 0 | 1 | Style sheet |

---

## Major Improvements

### 1. Function-Level Call Graph (308 edges) 🎯

The first analysis had **zero** function call edges. Tree-sitter now produces accurate intra-file call graphs:

**Example call chains (from `handlers/system_handler.py`):**
- `call_openclaw_status` → `list_all_sessions` → `_http_get`
- `call_openclaw_status` → `_parse_status_response`
- `format_status_report` → `resolve_status`
- `tail_gateway_logs` → `resolve_status` → `_http_get`

**Example from `think_patterns.py`:**
- `detect_think_pattern` → calls to internal helper functions
- `parse_think_tag` → `extract_thinking` → pattern matching helpers

### 2. Export Relationships (477 edges) 🔗

Every function `def` or `export` keyword detected by Tree-sitter creates an `exports` edge from its containing file. This provides precise module boundary analysis:

- `edit-web.py` exports 56 functions to its file node
- `handlers/router.py` exports 3 routing functions
- `static/js/render.js` exports 28 JavaScript functions

### 3. Source-Line Accuracy (Line Numbers) 📍

Every function and class node includes `startLine` and `endLine` from the AST. Example from `edit-web.py`:
```
function:edit-web.py:_cfg (lines 13-17)
function:edit-web.py:inject_via_websocket (lines 30-65)
function:edit-web.py:edit_message (lines 225-260)
function:edit-web.py:Handler (class, lines 400-450)
function:edit-web.py:V6Server (class, lines 520-750)
```

### 4. Hierarchical Structure (643 contains edges) 🏗️

File→function containment is precise:
```
file:handlers/file_handler.py
  ├── function:handlers/file_handler.py:load_file (lines 17-34)
  ├── function:handlers/file_handler.py:save_file (lines 37-55)
  ├── function:handlers/file_handler.py:delete_file (lines 58-73)
  ├── function:handlers/file_handler.py:list_files (lines 76-95)
  ├── function:handlers/file_handler.py:read_file_safe (lines 98-115)
  ├── function:handlers/file_handler.py:stream_file (lines 118-135)
  ├── function:handlers/file_handler.py:validate_path (lines 138-150)
  ├── function:handlers/file_handler.py:FileHandler (class, lines 153-210)
  └── function:handlers/file_handler.py:create_handler (lines 213-218)
```

---

## Project Architecture Summary (from Deep Analysis)

### Python Backend (516 function nodes)

| Module | Functions | Key Actors |
|---|---|---|
| `edit-web.py` | 56 | WebSocket gateway, injection, encryption, subagent execution |
| `handlers/` (8 files) | ~54 | Session, crypto, file, inject, awake, system, momo, router |
| `utils/` (8 files) | ~40 | Config, crypto, inject, momo, secretary, session, TB handler, version |
| `think_*.py` (4 files) | ~25 | Pattern detection, patching, type checking, testing |
| `static/js/*.js` (12 files) | ~184 | Frontend: editor, render, core, file-browser, momo, cache, subagent |

### Top Functions by Complexity
Most complex files (lines of code per function):
- `edit-web.py`: ~35 LOC/function avg — many handler endpoints
- `think_patterns.py`: ~40 LOC/fn — complex regex/pattern matching logic
- `static/js/render.js`: ~23 LOC/fn — rendering pipeline

---

## Key Differences vs First Analysis

### What the Deep Analysis Does Better:
1. **AST precision** — No LLM hallucination of function signatures or summaries
2. **Call graph** — 308 verified function-level call edges vs 0 before
3. **Export tracking** — 477 precise export edges vs 0 before
4. **Line-level accuracy** — Every function/class has exact source positions
5. **Deterministic** — Same code → same graph every time

### What the First Analysis Did That This Lacks:
1. **Cross-file import resolution** — 87 import edges (LLM could infer relationships that Tree-sitter alone can't resolve across files)
2. **Semantic summaries** — LLM could write "this function manages session lifecycle" — Tree-sitter only provides structural data
3. **Architecture layers** — LLM grouped files into layers (frontend, backend, utils, handlers)
4. **Guided tour** — LLM could create an onboarding flow through the codebase
5. **Tags/concepts** — LLM could add explanatory tags like "middleware", "encryption", "websocket"

---

## Configuration & Setup Notes

- **Ignore file** was refined to exclude 103 files from 201 scanned:
  - `backup_*/` directories excluded (96 files)
  - `.bak`, `.bak.*` extensions excluded
  - Specific legacy files excluded
  - `.踱步/` (temp directory) excluded
- Final analysis corpus: **98 files** across 7 languages
- Tree-sitter parsers loaded successfully for 12 languages (only skipped Kotlin)

---

## Recommendations

1. **Merge both approaches**: Use Tree-sitter for structural ground truth (call graphs, exports, containment), then use LLM to add semantic enrichment (summaries, layers, tours, cross-file import resolution)
2. **Add cross-file import resolution** via the `extract-import-map.mjs` script (available in SKILL_DIR but requires CLI option adjustment)
3. **File deduplication**: 5 copies of `edit-web.py` exist across revisions — the `revisions/` directory should be excluded or deduplicated
4. **Dashboard visualization**: The deep graph (652 KB) can be loaded into the Understand Anything interactive dashboard — the `contains` + `calls` + `exports` edge types are the three the dashboard's graph visualizer handles best

---

## Graph File Locations

| File | Path |
|---|---|
| Deep (Tree-sitter) | `/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/knowledge-graph/knowledge-graph-deep.json` |
| First (LLM) | `/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/knowledge-graph/knowledge-graph.json` |
| Intermediate | `/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/.understand-anything/knowledge-graph.json` |

