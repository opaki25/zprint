from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionInput(Input):
    station_code: str = Field(max_length=32)
    source: Literal["QR", "USB"] = "QR"


class QuoteInput(Input):
    document_id: str
    copies: int = Field(default=1, ge=1, le=100, strict=True)
    mode: Literal["BW", "COLOUR"] = "BW"
    duplex: bool = False
    paper_size: Literal["A4"] = "A4"
    page_range: str = Field(default="", max_length=1000)


class JobInput(Input):
    quote_id: str


class PaymentInput(Input):
    job_id: str
    provider: Literal["MTN", "AIRTEL"]
    msisdn: str = Field(pattern=r"^\+2567[0-9]{8}$")


class Heartbeat(Input):
    state: Literal["READY", "UNKNOWN", "NOT_READY"]
    paper_status: Literal["SUFFICIENT", "UNKNOWN", "EMPTY"] = "UNKNOWN"
    toner_status: Literal["SUFFICIENT", "UNKNOWN", "EMPTY"] = "UNKNOWN"
    errors: list[str] = Field(default_factory=list, max_length=10)


class AgentEvent(Input):
    event_id: str = Field(min_length=16, max_length=80)
    state: Literal["PRINTING", "COMPLETED", "COMPLETION_UNCERTAIN", "PAUSED", "FAILED"]
    spooler_job_id: str | None = Field(default=None, max_length=100)
    detail: str = Field(default="", max_length=500)


class Settlement(Input):
    status: Literal["SUCCEEDED", "FAILED"]
