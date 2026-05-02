import pytest
from unittest.mock import MagicMock, patch
from cv_parser import extract_text


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
