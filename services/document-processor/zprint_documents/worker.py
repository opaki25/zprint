import json
import sys
from pathlib import Path
from pypdf import PdfReader, PdfWriter


def main():
    # Container provides the outer memory/CPU boundary; Linux child limits add defense in depth.
    if sys.platform != "win32":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        resource.setrlimit(resource.RLIMIT_FSIZE, (40 * 1024**2, 40 * 1024**2))
    source, destination, limit = sys.argv[1:]
    reader = PdfReader(source, strict=True)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
    if not 1 <= len(reader.pages) <= int(limit):
        raise ValueError("Document page limit exceeded")
    root = reader.trailer["/Root"]
    if any(k in root for k in ("/OpenAction", "/AA", "/AcroForm")) or "/Names" in root:
        raise ValueError("Active content, forms and embedded files are not supported")
    writer = PdfWriter()
    for page in reader.pages:
        if "/AA" in page or "/Annots" in page:
            raise ValueError("Annotated/interactive PDFs are not supported in Phase 1")
        # Force content stream decoding in bounded process to reject corrupt streams.
        if page.get_contents() is not None:
            page.get_contents().get_data()
        if float(page.mediabox.width) <= 0 or float(page.mediabox.height) <= 0:
            raise ValueError("Invalid page dimensions")
        writer.add_page(page)
    with Path(destination).open("wb") as output:
        writer.write(output)
    print(json.dumps({"page_count": len(reader.pages)}))


if __name__ == "__main__":
    main()
