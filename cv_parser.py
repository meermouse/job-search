import io
import fitz  # PyMuPDF
from docx import Document


def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    if ext == "docx":
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if ext == "txt":
        return file_bytes.decode("utf-8")
    raise ValueError(f"Unsupported file type: .{ext}. Use PDF, DOCX, or TXT.")
