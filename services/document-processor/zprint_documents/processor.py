import hashlib
import json
import subprocess
import sys


ERRORS = {
    "encrypted": "This PDF is password-protected. Export an unlocked PDF and try again.",
    "page_limit": "This PDF is empty or exceeds the allowed page limit.",
    "interactive": "This PDF contains unsupported interactive content, forms or attachments. Export a plain PDF and try again.",
    "annotations": "This PDF contains comments, drawings or other unsupported annotations. Flatten them into the pages and try again.",
    "invalid_pdf": "This PDF could not be read. Open it in a PDF reader, export a new PDF and try again.",
}


def process_pdf(source, target, max_pages):
    if source.read_bytes()[:5] != b"%PDF-":
        raise ValueError("File signature is not PDF")
    try:
        result = subprocess.run([sys.executable, "-m", "zprint_documents.worker", str(source), str(target), str(max_pages)],
                                capture_output=True, timeout=20, check=False)
    except subprocess.TimeoutExpired as exc:
        target.unlink(missing_ok=True)
        raise ValueError("This PDF took too long to process. Export a simpler PDF and try again.") from exc
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        target.unlink(missing_ok=True)
        raise ValueError("PDF processing was interrupted. Try a smaller PDF or contact the station operator.") from exc
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        raise ValueError(ERRORS.get(payload.get("error"), ERRORS["invalid_pdf"]))
    count = payload.get("page_count")
    if type(count) is not int or not 1 <= count <= max_pages:
        target.unlink(missing_ok=True)
        raise ValueError(ERRORS["invalid_pdf"])
    return count, hashlib.sha256(target.read_bytes()).hexdigest(), payload.get("warnings", [])
