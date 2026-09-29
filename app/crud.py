from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import models, schemas


def get_product(db: Session, product_id: int) -> models.Product | None:
    return db.get(models.Product, product_id)


def get_product_by_sku(db: Session, sku: str) -> models.Product | None:
    return db.query(models.Product).filter(models.Product.sku == sku).first()


def list_products(
    db: Session,
    search: str | None = None,
    category: str | None = None,
    low_stock: bool = False,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[models.Product], int]:
    query = db.query(models.Product)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(models.Product.name.ilike(like), models.Product.sku.ilike(like)))
    if category:
        query = query.filter(models.Product.category == category)
    if low_stock:
        query = query.filter(models.Product.stock_qty <= models.Product.reorder_level)

    total = query.count()
    items = query.order_by(models.Product.name).offset(skip).limit(limit).all()
    return items, total


def create_product(db: Session, data: schemas.ProductCreate) -> models.Product:
    product = models.Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product: models.Product, data: schemas.ProductUpdate) -> models.Product:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product: models.Product) -> None:
    db.delete(product)
    db.commit()
