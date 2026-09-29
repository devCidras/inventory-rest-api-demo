import csv
import io

from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import models, schemas

REQUIRED_COLUMNS = {"sku", "name", "category", "unit_price", "stock_qty"}


def export_products_csv(products: list[models.Product]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["sku", "name", "category", "unit_price", "stock_qty", "reorder_level"])
    for p in products:
        writer.writerow([p.sku, p.name, p.category, p.unit_price, p.stock_qty, p.reorder_level])
    return buffer.getvalue()


def import_products_csv(db: Session, file_content: str) -> schemas.ImportResult:
    reader = csv.DictReader(io.StringIO(file_content))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        return schemas.ImportResult(
            created=0, updated=0, errors=[f"Missing required columns: {', '.join(sorted(missing))}"]
        )

    created = updated = 0
    errors: list[str] = []

    for line_no, row in enumerate(reader, start=2):  # header is line 1
        sku = (row.get("sku") or "").strip()
        if not sku:
            errors.append(f"Line {line_no}: missing sku")
            continue

        try:
            raw_payload = {
                "sku": sku,
                "name": row["name"].strip(),
                "category": row["category"].strip(),
                "unit_price": float(row["unit_price"]),
                "stock_qty": int(row["stock_qty"]),
                "reorder_level": int(row.get("reorder_level") or 0),
            }
        except (ValueError, KeyError) as exc:
            errors.append(f"Line {line_no}: invalid data ({exc})")
            continue

        try:
            # Run every row through the same validation as the API
            # (positive price/stock, non-empty name/category, ...) so a CSV
            # import can't slip in data the REST endpoints would reject.
            validated = schemas.ProductCreate(**raw_payload)
        except ValidationError as exc:
            errors.append(f"Line {line_no}: {exc.errors()[0]['msg']}")
            continue

        payload = validated.model_dump()
        existing = db.query(models.Product).filter(models.Product.sku == sku).first()
        if existing:
            for field, value in payload.items():
                if field != "sku":
                    setattr(existing, field, value)
            updated += 1
        else:
            db.add(models.Product(**payload))
            created += 1

    db.commit()
    return schemas.ImportResult(created=created, updated=updated, errors=errors)
