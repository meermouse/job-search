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
- "job_titles": list of 2-3 most suitable UK job titles, ordered by fit
- "skills": list of up to 8 most distinctive technical and professional skills
- "search_queries": list of exactly 2-3 search strings for UK job boards

Rules for search_queries:
- Each query must be a specific, targeted phrase a recruiter would use, e.g. "Senior Data Engineer dbt" or "Clinical Pharmacist NHS"
- Combine the primary job title with the single most differentiating skill or sector
- Do NOT use generic single words like "Engineer" or "Manager" alone
- Do NOT repeat the same role with minor wording changes
- Prefer shorter phrases (2-4 words) that job boards handle well
- Order from most to least specific

CV:
{cv_text}"""


def analyse_cv(text: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _PROMPT.format(cv_text=text)}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    return json.loads(raw)
