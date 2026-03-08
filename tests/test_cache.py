# tests/test_cache.py
"""Tests for pdf_mcp.cache module - edge cases."""

import os
import time
import tempfile
from pathlib import Path

import pytest

from pdf_mcp.cache import PDFCache


@pytest.fixture
def cache_with_data(cache, sample_pdf):
    """Cache pre-populated with test data."""
    cache.save_metadata(sample_pdf, 5, {"title": "Test"}, [])
    cache.save_page_text(sample_pdf, 0, "Page 1 content")
    cache.save_page_text(sample_pdf, 1, "Page 2 content")
    return cache, sample_pdf


class TestCacheValidation:
    """Tests for cache validation edge cases."""

    def test_is_cache_valid_file_deleted(self, cache):
        """Deleted file returns False for cache validity."""
        # Create temp file, cache it, then delete
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4")
            temp_path = f.name

        # Get mtime before deletion
        mtime = os.stat(temp_path).st_mtime

        # Delete the file
        os.unlink(temp_path)

        # _is_cache_valid should return False (OSError)
        result = cache._is_cache_valid(temp_path, mtime)
        assert result is False

    def test_get_metadata_invalidates_on_mtime_change(self, cache, sample_pdf):
        """Changed file mtime invalidates cached metadata."""
        # Save metadata
        cache.save_metadata(sample_pdf, 5, {"title": "Test"}, [])

        # Verify it's cached
        assert cache.get_metadata(sample_pdf) is not None

        # Touch the file to change mtime
        time.sleep(0.1)
        Path(sample_pdf).touch()

        # Should return None and invalidate
        result = cache.get_metadata(sample_pdf)
        assert result is None

    def test_get_page_text_invalid_mtime(self, cache, sample_pdf):
        """Page text with wrong mtime returns None."""
        cache.save_page_text(sample_pdf, 0, "Content")

        # Touch file to change mtime
        time.sleep(0.1)
        Path(sample_pdf).touch()

        result = cache.get_page_text(sample_pdf, 0)
        assert result is None

    def test_get_page_images_invalid_mtime(self, cache, sample_pdf):
        """Page images with wrong mtime returns None."""
        cache.save_page_images(
            sample_pdf,
            0,
            [
                {
                    "index": 0,
                    "width": 100,
                    "height": 100,
                    "format": "rgb",
                    "path": "/tmp/test.png",
                    "size_bytes": 100,
                }
            ],
        )

        # Touch file
        time.sleep(0.1)
        Path(sample_pdf).touch()

        result = cache.get_page_images(sample_pdf, 0)
        assert result is None


class TestEmptyInputs:
    """Tests for empty input handling."""

    def test_get_pages_text_empty_list(self, cache, sample_pdf):
        """Empty page list returns empty dict."""
        result = cache.get_pages_text(sample_pdf, [])
        assert result == {}

    def test_save_pages_text_empty_dict(self, cache, sample_pdf):
        """Empty pages dict is a no-op."""
        # Should not raise
        cache.save_pages_text(sample_pdf, {})

        # Verify nothing was saved
        stats = cache.get_stats()
        assert stats["total_pages"] == 0


class TestCacheInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_file_clears_all_tables(self, cache_with_data):
        """_invalidate_file removes data from all tables."""
        cache, sample_pdf = cache_with_data

        # Add images too
        cache.save_page_images(
            sample_pdf,
            0,
            [
                {
                    "index": 0,
                    "width": 10,
                    "height": 10,
                    "format": "rgb",
                    "path": "/tmp/test.png",
                    "size_bytes": 100,
                }
            ],
        )

        # Verify data exists
        assert cache.get_metadata(sample_pdf) is not None

        # Manually invalidate
        cache._invalidate_file(sample_pdf)

        # All data should be gone
        stats = cache.get_stats()
        assert stats["total_files"] == 0
        assert stats["total_pages"] == 0
        assert stats["total_images"] == 0

    def test_get_page_images_returns_path(self, cache, sample_pdf, tmp_path):
        """Cached images return path and size_bytes, not base64 data."""
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x89PNG fake")

        cache.save_page_images(
            sample_pdf,
            0,
            [
                {
                    "index": 0,
                    "width": 100,
                    "height": 100,
                    "format": "rgb",
                    "path": str(img_file),
                    "size_bytes": 9,
                }
            ],
        )
        result = cache.get_page_images(sample_pdf, 0)
        assert result is not None
        assert len(result) == 1
        assert "path" in result[0]
        assert "size_bytes" in result[0]
        assert result[0]["size_bytes"] == 9
        assert "data" not in result[0]
        assert result[0]["path"] == str(img_file)

    def test_get_page_images_cache_miss_when_file_missing(self, cache, sample_pdf):
        """DB row exists but PNG file missing on disk -> cache miss (None)."""
        cache.save_page_images(
            sample_pdf,
            0,
            [
                {
                    "index": 0,
                    "width": 100,
                    "height": 100,
                    "format": "rgb",
                    "path": "/nonexistent/deleted.png",
                    "size_bytes": 100,
                }
            ],
        )
        result = cache.get_page_images(sample_pdf, 0)
        assert result is None

    def test_get_stats_includes_image_dir_size(self, cache, tmp_path):
        """get_stats reports combined DB + image directory size."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        # Create a fake image file
        (images_dir / "test.png").write_bytes(b"x" * 1000)

        cache.images_dir = images_dir
        stats = cache.get_stats()
        # Should include the 1000-byte file
        assert stats["cache_size_bytes"] >= 1000

    def test_clear_all_deletes_image_files(self, cache, tmp_path):
        """clear_all() removes all PNG files from images directory."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        (images_dir / "abc_p0_i0.png").write_bytes(b"\x89PNG")
        (images_dir / "def_p1_i0.png").write_bytes(b"\x89PNG")
        cache.images_dir = images_dir

        cache.clear_all()

        assert not any(images_dir.iterdir())  # dir exists but empty

    def test_invalidate_file_deletes_image_files(self, cache, sample_pdf, tmp_path):
        """_invalidate_file() deletes PNGs for that file."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        png = images_dir / "abc_p0_i0.png"
        png.write_bytes(b"\x89PNG")
        cache.images_dir = images_dir

        cache.save_page_images(
            sample_pdf,
            0,
            [
                {
                    "index": 0,
                    "width": 10,
                    "height": 10,
                    "format": "rgb",
                    "path": str(png),
                    "size_bytes": 4,
                }
            ],
        )
        cache._invalidate_file(sample_pdf)

        assert not png.exists()

    def test_clear_expired_deletes_image_files(self, cache, sample_pdf, tmp_path):
        """clear_expired() deletes PNGs for expired entries."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        png = images_dir / "abc_p0_i0.png"
        png.write_bytes(b"\x89PNG")
        cache.images_dir = images_dir

        # Save with very short TTL cache (already ttl_hours=1 in fixture)
        cache.save_page_images(
            sample_pdf,
            0,
            [
                {
                    "index": 0,
                    "width": 10,
                    "height": 10,
                    "format": "rgb",
                    "path": str(png),
                    "size_bytes": 4,
                }
            ],
        )
        cache.save_metadata(sample_pdf, 1, {}, [])

        # Manually backdate the accessed_at to force expiration
        import sqlite3

        with sqlite3.connect(cache.db_path) as conn:
            conn.execute("UPDATE pdf_metadata SET accessed_at = '2020-01-01T00:00:00'")

        cache.clear_expired()
        assert not png.exists()

    def test_init_clears_expired_on_startup(self, tmp_path):
        """New PDFCache instance prunes expired entries on init."""
        cache1 = PDFCache(cache_dir=tmp_path, ttl_hours=1)
        images_dir = tmp_path / "images"
        images_dir.mkdir(exist_ok=True)
        png = images_dir / "old_p0_i0.png"
        png.write_bytes(b"\x89PNG")

        # Create sample PDF for metadata
        import pymupdf, tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            doc = pymupdf.open()
            doc.new_page()
            doc.save(f.name)
            doc.close()
            pdf_path = f.name

        cache1.save_metadata(pdf_path, 1, {}, [])
        cache1.save_page_images(
            pdf_path,
            0,
            [
                {
                    "index": 0,
                    "width": 10,
                    "height": 10,
                    "format": "rgb",
                    "path": str(png),
                    "size_bytes": 4,
                }
            ],
        )

        # Backdate to force expiry
        import sqlite3

        with sqlite3.connect(cache1.db_path) as conn:
            conn.execute("UPDATE pdf_metadata SET accessed_at = '2020-01-01'")

        # New cache instance should auto-prune on init
        cache2 = PDFCache(cache_dir=tmp_path, ttl_hours=1)

        stats = cache2.get_stats()
        assert stats["total_files"] == 0
        assert not png.exists()

        os.unlink(pdf_path)

    def test_save_page_images_cleans_stale_files(self, cache, sample_pdf, tmp_path):
        """Re-saving images for a page deletes old PNGs first."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        cache.images_dir = images_dir

        png0 = images_dir / "abc_p0_i0.png"
        png1 = images_dir / "abc_p0_i1.png"
        png0.write_bytes(b"\x89PNG img0")
        png1.write_bytes(b"\x89PNG img1")

        # Initial save with 2 images -> creates DB rows with file paths
        cache.save_page_images(
            sample_pdf,
            0,
            [
                {
                    "index": 0,
                    "width": 10,
                    "height": 10,
                    "format": "rgb",
                    "path": str(png0),
                    "size_bytes": 9,
                },
                {
                    "index": 1,
                    "width": 10,
                    "height": 10,
                    "format": "rgb",
                    "path": str(png1),
                    "size_bytes": 9,
                },
            ],
        )

        # Re-save with only 1 image — old DB rows queried, old files deleted
        new_png = images_dir / "abc_p0_i0.png"
        new_png.write_bytes(b"\x89PNG new")
        cache.save_page_images(
            sample_pdf,
            0,
            [
                {
                    "index": 0,
                    "width": 10,
                    "height": 10,
                    "format": "rgb",
                    "path": str(new_png),
                    "size_bytes": 8,
                },
            ],
        )

        # Old orphan i1 should be deleted
        assert not png1.exists()

    def test_mtime_change_invalidates_on_access(self, cache, sample_pdf):
        """Accessing stale cache triggers invalidation."""
        cache.save_metadata(sample_pdf, 5, {}, [])
        cache.save_page_text(sample_pdf, 0, "Content")

        # Change file
        time.sleep(0.1)
        Path(sample_pdf).touch()

        # Access triggers invalidation
        cache.get_metadata(sample_pdf)

        # Metadata should be cleared (though page_text cleanup is separate)
        stats = cache.get_stats()
        assert stats["total_files"] == 0
