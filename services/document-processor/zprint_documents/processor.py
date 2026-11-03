import hashlib
import json
import subprocess
import sys


def process_pdf(source, target, max_pages):
    if source.read_bytes()[:5] != b"%PDF-":
        raise ValueError("File signature is not PDF")
    try:
        result = subprocess.run([sys.executable, "-m", "zprint_documents.worker", str(source), str(target), str(max_pages)],
                                capture_output=True, timeout=20, check=True)
        count = json.loads(result.stdout)["page_count"]
        return count, hashlib.sha256(target.read_bytes()).hexdigest()
    except (subprocess.SubprocessError, ValueError, KeyError) as exc:
        target.unlink(missing_ok=True)
        raise ValueError("PDF cannot be processed safely (encrypted, active, corrupt or over limits)") from exc
