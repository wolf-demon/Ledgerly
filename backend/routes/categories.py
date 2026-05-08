"""Category CRUD endpoints."""
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException

from app_db import db
from models import Category, CategoryCreate, CategoryUpdate

router = APIRouter()


@router.get("/categories", response_model=List[Category])
async def list_categories(project_id: str):
    docs = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(1000)
    for d in docs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return docs


@router.post("/categories", response_model=Category)
async def create_category(payload: CategoryCreate):
    if payload.type not in ("income", "expense"):
        raise HTTPException(status_code=400, detail="type must be 'income' or 'expense'")
    cat = Category(**payload.model_dump())
    doc = cat.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.categories.insert_one(doc)
    return cat


@router.put("/categories/{category_id}", response_model=Category)
async def update_category(category_id: str, payload: CategoryUpdate):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if update:
        await db.categories.update_one({"id": category_id}, {"$set": update})
    doc = await db.categories.find_one({"id": category_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    if isinstance(doc.get('created_at'), str):
        doc['created_at'] = datetime.fromisoformat(doc['created_at'])
    return doc


@router.delete("/categories/{category_id}")
async def delete_category(category_id: str):
    await db.categories.delete_one({"id": category_id})
    await db.transactions.update_many({"category_id": category_id}, {"$set": {"category_id": None}})
    await db.rules.delete_many({"category_id": category_id})
    await db.budgets.delete_many({"category_id": category_id})
    return {"ok": True}
