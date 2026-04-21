import pytest

from app.services.chunking import chunk_text


class TestChunking:
    def test_empty_text(self):
        assert chunk_text("") == []

    def test_whitespace_only(self):
        assert chunk_text("   \n\n  ") == []

    def test_short_text_single_chunk(self):
        text = "This is a short paragraph."
        chunks = chunk_text(text, chunk_size=100, overlap=0)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_multiple_paragraphs(self):
        text = ("First paragraph. " * 50 + "\n\n" + "Second paragraph. " * 50)
        chunks = chunk_text(text, chunk_size=100, overlap=0)
        assert len(chunks) >= 2

    def test_overlap_produces_more_content(self):
        text = ("Some content here. " * 50 + "\n\n" + "More content here. " * 50)
        chunks_no_overlap = chunk_text(text, chunk_size=100, overlap=0)
        chunks_with_overlap = chunk_text(text, chunk_size=100, overlap=20)
        # With overlap, later chunks should start with content from previous chunk
        if len(chunks_with_overlap) > 1:
            assert len(chunks_with_overlap[1]) > len(chunks_no_overlap[1]) if len(chunks_no_overlap) > 1 else True

    def test_no_empty_chunks(self):
        text = "Hello world.\n\n\n\n\nAnother section.\n\n\n\nFinal part."
        chunks = chunk_text(text, chunk_size=500, overlap=0)
        for chunk in chunks:
            assert chunk.strip() != ""

    def test_long_paragraph_gets_split(self):
        text = "This is a sentence. " * 200  # Very long single paragraph
        chunks = chunk_text(text, chunk_size=50, overlap=0)
        assert len(chunks) > 1
