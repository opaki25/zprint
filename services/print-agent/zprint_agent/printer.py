import os
from pathlib import Path
from typing import Protocol
from pypdf import PdfReader, PdfWriter


class PrinterAdapter(Protocol):
    def readiness(self) -> dict: ...
    def submit(self, job_id: str, pdf: Path, settings: dict) -> str: ...
    def status(self, spooler_id: str) -> str: ...


class SimulatedPrinter:
    """Writes actual selected pages/copies to a private spool directory; no physical claims."""
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def readiness(self):
        control = self.directory.parent / "printer-state.txt"
        state = control.read_text().strip() if control.exists() else os.getenv("ZPRINT_PRINTER_STATE", "READY")
        if state not in ("READY", "UNKNOWN", "NOT_READY"):
            state = "NOT_READY"
        return {"state": state, "paper_status": "SUFFICIENT" if state == "READY" else "UNKNOWN",
                "toner_status": "SUFFICIENT" if state == "READY" else "UNKNOWN", "errors": [] if state == "READY" else [state]}

    def submit(self, job_id, pdf, settings):
        if self.readiness()["state"] != "READY":
            raise RuntimeError("Printer became unavailable")
        if settings["mode"] != "BW" or settings["paper_size"] != "A4":
            raise ValueError("Simulated printer supports BW/A4 only")
        reader, writer = PdfReader(pdf), PdfWriter()
        for _ in range(settings["copies"]):
            for number in settings["pages"]:
                writer.add_page(reader.pages[number - 1])
            if settings["duplex"] and len(settings["pages"]) % 2:
                writer.add_blank_page(width=595.28, height=841.89)
        writer.add_metadata({"/Title": "Z-PRINT SIMULATED OUTPUT", "/ZPrintMode": "BW", "/ZPrintDuplex": str(settings["duplex"])})
        output = self.directory / f"{job_id}.pdf"
        # Exclusive creation: an existing output is ambiguous and must never be overwritten/reprinted.
        with output.open("xb") as stream:
            writer.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        return output.name

    def status(self, spooler_id):
        return "SIMULATED_COMPLETE" if (self.directory / spooler_id).is_file() else "UNKNOWN"


class CupsPrinter:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Real CUPS/IPP requires verified model, media, colour, duplex and completion telemetry; see docs/integrations.md")
