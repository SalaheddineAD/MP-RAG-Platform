from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


class DocumentLoader:
    """Load manufacturing documents from uploaded file bytes."""

    SUPPORTED = {".pdf", ".txt", ".md", ".markdown"}

    @staticmethod
    def load_file(content: bytes, filename: str) -> str:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in DocumentLoader.SUPPORTED:
            raise ValueError(
                f"Unsupported file type '{suffix}'. "
                f"Supported: {', '.join(sorted(DocumentLoader.SUPPORTED))}"
            )

        if suffix == ".pdf":
            return DocumentLoader._load_pdf(content)
        return content.decode("utf-8", errors="replace")

    @staticmethod
    def _load_pdf(content: bytes) -> str:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages).strip()
        if not text:
            raise ValueError("No extractable text found in PDF")
        return text
