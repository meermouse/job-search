import json
import pytest
from unittest.mock import MagicMock
from cv_parser import extract_text, analyse_cv


def test_extract_text_txt():
    content = "John Smith\nSoftware Engineer\nPython, Django"
    result = extract_text(content.encode("utf-8"), "cv.txt")
    assert result == content


def test_extract_text_pdf(mocker):
    mock_page = MagicMock()
    mock_page.get_text.return_value = "PDF content line"
    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
    mocker.patch("fitz.open", return_value=mock_doc)

    result = extract_text(b"%PDF fake bytes", "cv.pdf")
    assert result == "PDF content line"


def test_extract_text_docx(mocker):
    mock_para1 = MagicMock()
    mock_para1.text = "Jane Doe"
    mock_para2 = MagicMock()
    mock_para2.text = ""
    mock_para3 = MagicMock()
    mock_para3.text = "Data Scientist"
    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]
    mocker.patch("cv_parser.Document", return_value=mock_doc)

    result = extract_text(b"PK fake docx bytes", "cv.docx")
    assert result == "Jane Doe\nData Scientist"


def test_extract_text_unsupported_format():
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text(b"data", "cv.odt")


def test_analyse_cv_returns_structured_data(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    expected = {
        "job_titles": ["Data Engineer", "Backend Developer"],
        "skills": ["Python", "SQL", "AWS"],
        "search_queries": ["Data Engineer Bristol", "Backend Developer Python Bristol"],
    }
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(expected))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("cv_parser.anthropic.Anthropic", return_value=mock_client)

    result = analyse_cv("John Smith, Software Engineer with 5 years Python experience.")
    assert result["job_titles"] == ["Data Engineer", "Backend Developer"]
    assert "Python" in result["skills"]
    assert len(result["search_queries"]) == 2


def test_analyse_cv_raises_on_api_error(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")
    mocker.patch("cv_parser.anthropic.Anthropic", return_value=mock_client)

    with pytest.raises(Exception, match="API unavailable"):
        analyse_cv("Some CV text")
