import io
import json
import os
import anthropic
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


_SYSTEM = "You extract structured job search data from CVs. Return only valid JSON, no markdown."

_PROMPT = """\
Analyse this CV and return a JSON object with exactly these keys:
- "job_titles": list of 3-5 suitable UK job titles based on experience
- "skills": list of key technical and professional skills
- "search_queries": list of 3-5 search strings for UK job boards

CV:
{cv_text}"""


def analyse_cv(text: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _PROMPT.format(cv_text=text)}],
    )
    return json.loads(msg.content[0].text)
