import io
import os

os.environ.setdefault("API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


HEADERS = {"X-API-Key": "test-key"}
client = TestClient(app)


def test_health_is_public():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_products_require_api_key():
    resp = client.get("/products")
    assert resp.status_code == 401


def test_create_list_get_update_delete_product():
    payload = {
        "sku": "ABC-1",
        "name": "Chair",
        "category": "Furniture",
        "unit_price": 89.9,
        "stock_qty": 10,
        "reorder_level": 5,
    }
    created = client.post("/products", json=payload, headers=HEADERS)
    assert created.status_code == 201
    product_id = created.json()["id"]

    dup = client.post("/products", json=payload, headers=HEADERS)
    assert dup.status_code == 409

    listed = client.get("/products", headers=HEADERS)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = client.get(f"/products/{product_id}", headers=HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["sku"] == "ABC-1"

    updated = client.put(f"/products/{product_id}", json={"stock_qty": 3}, headers=HEADERS)
    assert updated.status_code == 200
    assert updated.json()["stock_qty"] == 3
    assert updated.json()["name"] == "Chair"  # untouched fields stay as-is

    null_update = client.put(f"/products/{product_id}", json={"name": None}, headers=HEADERS)
    assert null_update.status_code == 422

    deleted = client.delete(f"/products/{product_id}", headers=HEADERS)
    assert deleted.status_code == 204

    missing = client.get(f"/products/{product_id}", headers=HEADERS)
    assert missing.status_code == 404


def test_validation_rejects_negative_price():
    payload = {
        "sku": "BAD-1",
        "name": "Invalid Item",
        "category": "X",
        "unit_price": -5,
        "stock_qty": 10,
        "reorder_level": 5,
    }
    resp = client.post("/products", json=payload, headers=HEADERS)
    assert resp.status_code == 422


def test_csv_import_and_export():
    csv_content = (
        "sku,name,category,unit_price,stock_qty,reorder_level\n"
        "SKU-1,Monitor,Electronics,139.5,20,10\n"
        "SKU-2,Mouse,Electronics,24.9,4,10\n"
    )
    files = {"file": ("products.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = client.post("/products/import", files=files, headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["errors"] == []

    # Re-importing the same file should update, not duplicate.
    resp2 = client.post("/products/import", files=files, headers=HEADERS)
    assert resp2.json()["updated"] == 2

    export = client.get("/products/export", headers=HEADERS)
    assert export.status_code == 200
    assert "SKU-1" in export.text
    assert "SKU-2" in export.text


def test_csv_import_reports_row_errors():
    csv_content = "sku,name,category,unit_price,stock_qty,reorder_level\nOK-1,Item,Cat,10,5,2\n,Item without sku,Cat,10,5,2\nBAD-2,Item,Cat,not-a-number,5,2\n"
    files = {"file": ("products.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = client.post("/products/import", files=files, headers=HEADERS)
    body = resp.json()
    assert body["created"] == 1
    assert len(body["errors"]) == 2


def test_csv_import_rejects_invalid_rows_like_the_api_does():
    csv_content = (
        "sku,name,category,unit_price,stock_qty,reorder_level\n"
        "GOOD-1,Good Item,Cat,10,5,2\n"
        "NEG-PRICE,Bad Price Item,Cat,-5,5,2\n"
        "EMPTY-NAME,,Cat,10,5,2\n"
    )
    files = {"file": ("products.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = client.post("/products/import", files=files, headers=HEADERS)
    body = resp.json()
    assert body["created"] == 1
    assert len(body["errors"]) == 2

    listed = client.get("/products", headers=HEADERS).json()["items"]
    skus = {p["sku"] for p in listed}
    assert "NEG-PRICE" not in skus
    assert "EMPTY-NAME" not in skus


def test_low_stock_filter():
    client.post(
        "/products",
        json={"sku": "LOW-1", "name": "Low Stock Item", "category": "X", "unit_price": 10, "stock_qty": 1, "reorder_level": 5},
        headers=HEADERS,
    )
    client.post(
        "/products",
        json={"sku": "OK-1", "name": "Healthy Stock Item", "category": "X", "unit_price": 10, "stock_qty": 50, "reorder_level": 5},
        headers=HEADERS,
    )
    resp = client.get("/products", params={"low_stock": True}, headers=HEADERS)
    skus = [p["sku"] for p in resp.json()["items"]]
    assert skus == ["LOW-1"]
