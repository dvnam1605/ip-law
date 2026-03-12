"""
Trademark PostgreSQL Ingestion
Import crawled trademark data (JSON) into PostgreSQL.

Usage:
    python -m utils.trademark_pg_ingest data/trademarks/all_vn_trademarks.json
    python -m utils.trademark_pg_ingest data/trademarks/batch_full.json --batch-size 500
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.db.database import DATABASE_URL
from backend.db.models import Base, Trademark, NiceClass, trademark_nice_class

logger = logging.getLogger(__name__)


class TrademarkPGIngestor:

    def __init__(self, database_url: str = None):
        url = database_url or DATABASE_URL
        self.engine = create_async_engine(url, echo=False)
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def setup(self):
        """Create tables and extensions."""
        async with self.engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables and extensions ready")

    async def close(self):
        await self.engine.dispose()

    async def _ensure_nice_classes(self, session: AsyncSession, class_numbers: list[str]) -> dict[str, int]:
        """Get or create NiceClass rows, return {class_number: id}."""
        if not class_numbers:
            return {}

        # Upsert all nice classes
        for cn in class_numbers:
            stmt = pg_insert(NiceClass).values(class_number=cn).on_conflict_do_nothing(
                index_elements=["class_number"]
            )
            await session.execute(stmt)

        # Fetch ids
        result = await session.execute(
            select(NiceClass).where(NiceClass.class_number.in_(class_numbers))
        )
        return {nc.class_number: nc.id for nc in result.scalars().all()}

    async def ingest_records(self, records: list[dict], batch_size: int = 500):
        """Ingest trademark records into PostgreSQL."""
        await self.setup()

        total = len(records)
        logger.info(f"Ingesting {total} records (batch_size={batch_size})...")

        # Collect all unique nice classes first
        all_nice = set()
        for rec in records:
            for nc in (rec.get("nice_classes") or []):
                all_nice.add(str(nc).strip())

        async with self.session_factory() as session:
            nice_map = await self._ensure_nice_classes(session, list(all_nice))
            await session.commit()

        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            async with self.session_factory() as session:
                for rec in batch:
                    brand_name = str(rec.get("brand_name", "") or "").strip()
                    if not brand_name:
                        continue

                    merge_key = rec.get("st13") or rec.get("registration_number") or ""
                    if not merge_key:
                        continue

                    # Upsert trademark
                    values = {
                        "brand_name": brand_name,
                        "brand_name_lower": brand_name.lower(),
                        "st13": rec.get("st13") or None,
                        "registration_number": rec.get("registration_number") or None,
                        "application_number": rec.get("application_number") or None,
                        "status": rec.get("status") or None,
                        "status_date": rec.get("status_date") or None,
                        "ip_office": rec.get("ip_office") or None,
                        "feature": rec.get("feature") or None,
                        "ipr_type": rec.get("ipr_type") or None,
                        "country_of_filing": rec.get("country_of_filing") or None,
                        "registration_date": rec.get("registration_date") or None,
                        "application_date": rec.get("application_date") or None,
                        "expiry_date": rec.get("expiry_date") or None,
                        "owner_name": rec.get("owner_name") or None,
                        "owner_country": rec.get("owner_country") or None,
                        "crawled_at": rec.get("crawled_at") or None,
                    }

                    if values["st13"]:
                        stmt = pg_insert(Trademark).values(**values).on_conflict_do_update(
                            index_elements=["st13"],
                            set_={k: v for k, v in values.items() if k != "st13"},
                        )
                    else:
                        # No st13 — check by registration_number
                        existing = await session.execute(
                            select(Trademark).where(
                                Trademark.registration_number == values["registration_number"]
                            )
                        )
                        row = existing.scalar_one_or_none()
                        if row:
                            for k, v in values.items():
                                if v is not None:
                                    setattr(row, k, v)
                            await session.flush()
                            tm_id = row.id
                        else:
                            new_tm = Trademark(**values)
                            session.add(new_tm)
                            await session.flush()
                            tm_id = new_tm.id

                        # Handle nice classes for non-st13
                        nice_classes = [str(nc).strip() for nc in (rec.get("nice_classes") or [])]
                        if nice_classes:
                            for cn in nice_classes:
                                nc_id = nice_map.get(cn)
                                if nc_id:
                                    await session.execute(
                                        pg_insert(trademark_nice_class).values(
                                            trademark_id=tm_id, nice_class_id=nc_id
                                        ).on_conflict_do_nothing()
                                    )
                        continue

                    result = await session.execute(stmt)
                    await session.flush()

                    # Get trademark id
                    if values["st13"]:
                        tm_row = await session.execute(
                            select(Trademark.id).where(Trademark.st13 == values["st13"])
                        )
                        tm_id = tm_row.scalar_one()

                    # Handle nice classes
                    nice_classes = [str(nc).strip() for nc in (rec.get("nice_classes") or [])]
                    if nice_classes:
                        for cn in nice_classes:
                            nc_id = nice_map.get(cn)
                            if nc_id:
                                await session.execute(
                                    pg_insert(trademark_nice_class).values(
                                        trademark_id=tm_id, nice_class_id=nc_id
                                    ).on_conflict_do_nothing()
                                )

                await session.commit()

            logger.info(f"  Ingested {min(i + batch_size, total)}/{total}")

        logger.info(f"✅ Ingestion complete: {total} records")

    async def ingest_from_file(self, json_path: str, batch_size: int = 500):
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)

        logger.info(f"Loaded {len(records)} records from {json_path}")
        await self.ingest_records(records, batch_size)

    async def get_count(self) -> int:
        async with self.session_factory() as session:
            result = await session.execute(select(func.count(Trademark.id)))
            return result.scalar_one()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import trademark data into PostgreSQL")
    parser.add_argument("input_file", help="JSON file with trademark records")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    ingestor = TrademarkPGIngestor()
    try:
        await ingestor.ingest_from_file(args.input_file, args.batch_size)
        count = await ingestor.get_count()
        logger.info(f"Total trademarks in DB: {count}")
    finally:
        await ingestor.close()


if __name__ == "__main__":
    asyncio.run(main())
