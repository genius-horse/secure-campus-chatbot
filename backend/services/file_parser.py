"""文件解析服务 — 支持 txt / md / pdf / docx，含 ZIP 炸弹防护。"""

import io
import zipfile
import os

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_UNCOMPRESSED = 100 * 1024 * 1024  # 100 MB ZIP bomb 限制
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


class FileParserError(ValueError):
    pass


def _check_zip_bomb(content: bytes) -> None:
    """检查 ZIP 内部文件解压后总大小不超过 MAX_UNCOMPRESSED。"""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            total = sum(info.file_size for info in zf.infolist())
            if total > MAX_UNCOMPRESSED:
                raise FileParserError(
                    f"ZIP 内含文件过大（{total / 1024 / 1024:.1f}MB），"
                    f"超过 {MAX_UNCOMPRESSED / 1024 / 1024:.0f}MB 限制"
                )
    except zipfile.BadZipFile:
        pass  # 非 ZIP 文件忽略


def _detect_encoding(content: bytes) -> str:
    for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace")


def _parse_text(content: bytes) -> str:
    return _detect_encoding(content)


def _parse_pdf(content: bytes) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(content))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n".join(parts) if parts else ""
    except ImportError:
        raise FileParserError("PDF 解析需要安装 PyPDF2：pip install PyPDF2>=3.0.0")
    except Exception as exc:
        raise FileParserError(f"PDF 解析失败：{exc}")


def _parse_docx(content: bytes) -> str:
    _check_zip_bomb(content)
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text)
        return "\n".join(parts) if parts else ""
    except ImportError:
        raise FileParserError("DOCX 解析需要安装 python-docx：pip install python-docx>=1.0.0")
    except Exception as exc:
        raise FileParserError(f"DOCX 解析失败：{exc}")


def parse_file(filename: str, content: bytes) -> str:
    """根据扩展名路由解析，返回文本内容。"""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileParserError(f"不支持的文件类型：{ext}。支持：{', '.join(ALLOWED_EXTENSIONS)}")

    if len(content) > MAX_FILE_SIZE:
        raise FileParserError(
            f"文件大小 {len(content) / 1024 / 1024:.1f}MB 超过 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB 限制"
        )

    if ext == ".txt" or ext == ".md":
        return _parse_text(content)
    elif ext == ".pdf":
        return _parse_pdf(content)
    elif ext == ".docx":
        return _parse_docx(content)
    else:
        raise FileParserError(f"不支持的文件类型：{ext}")


def extract_title(text: str, filename: str) -> str:
    """从文本首行或文件名提取标题。"""
    lines = text.strip().splitlines()
    if lines and lines[0].strip():
        first = lines[0].strip()
        # 去掉 markdown 标题标记
        while first and first[0] in "#*>- ":
            first = first[1:]
        first = first.strip()
        if len(first) <= 100:
            return first
    # 使用文件名（去掉扩展名）
    name = os.path.splitext(filename)[0]
    return name if name else "未命名文档"


def generate_kb_id(filename: str, title: str) -> str:
    """生成安全的知识库 ID。"""
    import re
    safe_title = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "", title)[:40]
    base = os.path.splitext(filename)[0]
    safe_base = re.sub(r"[^a-zA-Z0-9_-]", "", base)[:20]
    return f"upload-{safe_base}-{safe_title}" if safe_title else f"upload-{safe_base}"


def extract_keywords(text: str) -> list[str]:
    """简单中英文关键词提取。"""
    import re
    words = set()

    # 英文关键词（长度>=3的单词）
    eng = re.findall(r"[a-zA-Z]{3,}", text)
    for w in eng:
        if w.lower() not in {"the", "and", "for", "this", "that", "with", "from", "have", "are", "was",
                            "you", "all", "not", "but", "can", "has", "had", "been", "its", "also",
                            "very", "each", "what", "when", "where", "which", "about", "will"}:
            words.add(w.lower())

    # 中文关键词（长度>=2的连续短词组）
    chn = re.findall(r"[一-鿿]{2,4}", text)
    for w in chn[:20]:
        words.add(w)

    return list(words)[:10]
