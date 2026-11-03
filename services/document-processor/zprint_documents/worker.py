import json
import sys
from pathlib import Path
from pypdf import PdfReader, PdfWriter


class PDFRejected(ValueError):
    pass


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
        raise PDFRejected("encrypted")
    if not 1 <= len(reader.pages) <= int(limit):
        raise PDFRejected("page_limit")
    root = reader.trailer["/Root"]
    if any(k in root for k in ("/OpenAction", "/AA", "/AcroForm")) or "/Names" in root:
        raise PDFRejected("interactive")
    writer = PdfWriter()
    links_removed = False
    for page in reader.pages:
        if "/AA" in page:
            raise PDFRejected("interactive")
        for reference in page.get("/Annots", []):
            annotation = reference.get_object()
            if annotation.get("/Subtype") != "/Link":
                raise PDFRejected("annotations")
            if "/AA" in annotation:
                raise PDFRejected("interactive")
            action = annotation.get("/A")
            if action is not None:
                action = action.get_object()
                if action.get("/S") not in ("/URI", "/GoTo") or "/Next" in action:
                    raise PDFRejected("interactive")
            links_removed = True
        # Remove link references BEFORE cloning the page; no action dictionaries or
        # external destinations are carried into the print/preview document.
        if "/Annots" in page:
            del page["/Annots"]
        # Force content stream decoding in bounded process to reject corrupt streams.
        if page.get_contents() is not None:
            page.get_contents().get_data()
        if float(page.mediabox.width) <= 0 or float(page.mediabox.height) <= 0:
            raise ValueError("Invalid page dimensions")
        writer.add_page(page)
    with Path(destination).open("wb") as output:
        writer.write(output)
    print(json.dumps({"page_count": len(reader.pages), "warnings": ["Clickable links were removed from the print copy."] if links_removed else []}))


if __name__ == "__main__":
    try:
        main()
    except PDFRejected as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
    except Exception:
        # Never return arbitrary parser errors or document content to the client.
        print(json.dumps({"error": "invalid_pdf"}))
        sys.exit(2)
