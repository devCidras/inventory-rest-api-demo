"""Seeds the inventory database with an initial product catalog, so the API
isn't empty on first run."""

from app.database import Base, SessionLocal, engine
from app.models import Product

PRODUCTS = [
    ("CAD-001", "Office Chair", "Furniture", 89.90, 42, 15),
    ("SEC-002", "Adjustable Desk", "Furniture", 249.00, 8, 10),
    ("MON-003", "24in Monitor", "Electronics", 139.50, 27, 12),
    ("TEC-004", "Mechanical Keyboard", "Electronics", 59.90, 4, 15),
    ("RAT-005", "Wireless Mouse", "Electronics", 24.90, 55, 20),
    ("LED-006", "LED Desk Lamp", "Lighting", 34.50, 33, 10),
    ("EST-007", "Modular Shelving Unit", "Furniture", 119.00, 6, 8),
    ("AUS-008", "Bluetooth Headphones", "Electronics", 79.00, 18, 12),
    ("TAP-009", "XL Mouse Pad", "Accessories", 14.90, 61, 20),
    ("WEB-010", "HD Webcam", "Electronics", 44.90, 9, 10),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Product).count() > 0:
            print("Database already has products, nothing to do.")
            return
        for sku, name, category, price, stock, reorder in PRODUCTS:
            db.add(
                Product(
                    sku=sku,
                    name=name,
                    category=category,
                    unit_price=price,
                    stock_qty=stock,
                    reorder_level=reorder,
                )
            )
        db.commit()
        print(f"{len(PRODUCTS)} products inserted.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
