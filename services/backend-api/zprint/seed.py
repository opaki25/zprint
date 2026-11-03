from sqlalchemy import select
from zprint.config import Settings
from zprint.db import connect
from zprint.models import Agent, Printer, Station, Tier


def seed(factory, code="ST001"):
    with factory.begin() as db:
        if db.scalar(select(Station).where(Station.code == code)):
            return
        station = Station(code=code, name="Z-PRINT · Campus demo")
        db.add(station)
        db.flush()
        db.add(Printer(station_id=station.id))
        db.add(Agent(station_id=station.id))
        for mode, rates in (("BW", [300, 250, 200, 150]), ("COLOUR", [1000, 800, 700, 600])):
            for low, high, rate in zip([1, 10, 30, 100], [9, 29, 99, None], rates):
                db.add(Tier(station_id=station.id, mode=mode, min_sides=low, max_sides=high, rate_ugx=rate, version=1))


if __name__ == "__main__":
    cfg = Settings()
    cfg.validate()
    engine, factory = connect(cfg.database_url)
    seed(factory, cfg.station)
    engine.dispose()
    print("Seeded demo station (idempotent). Prices are illustrative.")
