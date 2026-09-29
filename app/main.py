"""Inventory REST API demo.

Problem it solves: a small business keeps its product/stock data in an
Excel file or a system with no API, so any other tool (a website, a
reporting dashboard, an internal script) can't read or update it without
someone exporting a file by hand.

This is a small, self-contained REST API on top of a real SQL database:
CRUD for products, search/filtering, CSV bulk import/export, simple API-key
auth, and interactive documentation generated automatically at /docs.

Run with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from . import crud, csv_io, schemas
from .auth import require_api_key
from .database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

# Seed the initial catalog if empty. This is idempotent (seed_data.main()
# is a no-op once products exist), which also makes the API deployable to
# a host with an ephemeral disk without a manual setup step.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import seed_data  # noqa: E402

seed_data.main()

app = FastAPI(
    title="Inventory API",
    description=(
        "Product & inventory management API demo: CRUD, search/filtering, "
        "CSV bulk import/export and simple API-key authentication."
    ),
    version="1.0.0",
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/products", response_model=schemas.ProductPage, tags=["products"])
def list_products(
    search: str | None = None,
    category: str | None = None,
    low_stock: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
) -> schemas.ProductPage:
    items, total = crud.list_products(db, search, category, low_stock, (page - 1) * page_size, page_size)
    return schemas.ProductPage(items=items, total=total, page=page, page_size=page_size)


@app.post(
    "/products",
    response_model=schemas.ProductOut,
    status_code=status.HTTP_201_CREATED,
    tags=["products"],
)
def create_product(
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
) -> schemas.ProductOut:
    if crud.get_product_by_sku(db, payload.sku):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"SKU '{payload.sku}' already exists")
    return crud.create_product(db, payload)


@app.get("/products/export", tags=["products"])
def export_products(db: Session = Depends(get_db), _: str = Depends(require_api_key)) -> StreamingResponse:
    products, _total = crud.list_products(db, limit=1_000_000)
    csv_text = csv_io.export_products_csv(products)
    return StreamingResponse(
        io.StringIO(csv_text),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products_export.csv"},
    )


@app.post("/products/import", response_model=schemas.ImportResult, tags=["products"])
async def import_products(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
) -> schemas.ImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a .csv")
    content = (await file.read()).decode("utf-8-sig")
    return csv_io.import_products_csv(db, content)


@app.get("/products/{product_id}", response_model=schemas.ProductOut, tags=["products"])
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
) -> schemas.ProductOut:
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@app.put("/products/{product_id}", response_model=schemas.ProductOut, tags=["products"])
def update_product(
    product_id: int,
    payload: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
) -> schemas.ProductOut:
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    updates = payload.model_dump(exclude_unset=True)
    null_fields = [field for field, value in updates.items() if value is None]
    if null_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Fields cannot be set to null: {', '.join(null_fields)}",
        )

    return crud.update_product(db, product, payload)


@app.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["products"])
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
) -> None:
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    crud.delete_product(db, product)
