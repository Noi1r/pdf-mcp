# pdf-mcp (fork)

> Fork of [jztan/pdf-mcp](https://github.com/jztan/pdf-mcp) with file-based image extraction instead of base64.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server for reading, searching, and extracting content from PDF files. Built with PyMuPDF, with SQLite caching.

## Fork Changes

### Problem

The upstream `pdf_extract_images` returns base64-encoded image data in the MCP tool result. In LLM contexts (Claude Code, Claude Desktop, etc.), this is wasteful:

- A single PDF page with 26 images produces ~740,000 characters of base64 ≈ **180,000 tokens**
- The LLM cannot interpret raw base64 strings as images — it's just noise
- The MCP server and caller run on the same machine (STDIO transport), so file paths work fine

### Solution

Images are now **always saved to disk** and **file paths** are returned instead of base64 data.

**Changed files:**

| File | Change |
|------|--------|
| `extractor.py` | `extract_images_from_page()` writes PNG files, returns `file_path`. Uses `tempfile.mkdtemp()` when no `output_dir` specified. |
| `server.py` | `pdf_extract_images` and `pdf_read_pages` both accept `output_dir` parameter. Cache integration on both paths. |
| `cache.py` | `page_images` table stores `image_path` (file path) instead of `data` (base64). Cache hit validates file still exists on disk. |

**Before (upstream):**
```json
{
  "images": [
    {"page": 1, "width": 800, "height": 600, "data": "iVBORw0KGgo... (500KB)"}
  ]
}
```

**After (this fork):**
```json
{
  "images": [
    {"page": 1, "width": 800, "height": 600, "file_path": "/path/to/page1_img0.png"}
  ]
}
```

### Behavior

| Scenario | Result |
|----------|--------|
| `output_dir` specified | Images saved to that directory |
| `output_dir` omitted | Images saved to auto-created temp directory |
| Repeated call, same page | Cache hit — returns previously saved file paths (skips re-extraction) |
| PDF modified after cache | Cache invalidated, images re-extracted |
| Cached image file deleted | Cache invalidated, images re-extracted |

## Installation

```bash
# From this fork
pip install git+https://github.com/Noi1r/pdf-mcp.git

# Or clone and install locally
git clone https://github.com/Noi1r/pdf-mcp.git
cd pdf-mcp
pip install -e .
```

## Quick Start

```bash
claude mcp add pdf-mcp -- pdf-mcp
```

Or add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "pdf-mcp": {
      "command": "pdf-mcp"
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `pdf_info` | Page count, metadata, TOC, file size. **Call first.** |
| `pdf_read_pages` | Read specific pages (supports `include_images` + `output_dir`) |
| `pdf_read_all` | Read entire document (small PDFs only) |
| `pdf_search` | Full-text search within PDF |
| `pdf_get_toc` | Table of contents / bookmarks |
| `pdf_extract_images` | Extract images to disk, return file paths |
| `pdf_cache_stats` | Cache statistics |
| `pdf_cache_clear` | Clear cache (expired or all) |

### Image Extraction Examples

```python
# Recommended: specify output directory
pdf_extract_images(path="paper.pdf", pages="1-3", output_dir="figures")

# Also works: auto temp directory
pdf_extract_images(path="paper.pdf", pages="5")

# With pdf_read_pages
pdf_read_pages(path="paper.pdf", pages="1-5", include_images=True, output_dir="images")
```

## Caching

SQLite-based cache at `~/.cache/pdf-mcp/cache.db`.

| Cached | Content |
|--------|---------|
| Metadata | Page count, author, TOC |
| Page text | Extracted text per page |
| Image paths | File paths + dimensions (not image data) |

Cache invalidates automatically when the PDF file is modified or when cached image files no longer exist on disk.

## Syncing with Upstream

```bash
git fetch upstream
git merge upstream/master
# Resolve conflicts in extractor.py / server.py / cache.py if any
```

## License

MIT — see [LICENSE](LICENSE).

## Links

- [Upstream repo](https://github.com/jztan/pdf-mcp)
- [MCP Documentation](https://modelcontextprotocol.io/)
