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
    if payload.parent_id:
        parent = await db.categories.find_one({"id": payload.parent_id, "project_id": payload.project_id}, {"_id": 0})
        if not parent:
            raise HTTPException(status_code=400, detail="Parent category not found in this project")
        if parent.get("parent_id"):
            raise HTTPException(status_code=400, detail="Sub-categories cannot themselves have parents (one level deep)")
    cat = Category(**payload.model_dump())
    doc = cat.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.categories.insert_one(doc)
    return cat


@router.put("/categories/{category_id}", response_model=Category)
async def update_category(category_id: str, payload: CategoryUpdate):
    update_raw = payload.model_dump()
    # Treat parent_id == "" as "clear parent".
    if update_raw.get("parent_id") == "":
        update_raw["parent_id"] = None
    update = {k: v for k, v in update_raw.items() if v is not None or k == "parent_id"}
    # Drop entries the caller didn't actually send.
    update = {k: v for k, v in update.items() if k in payload.model_fields_set or k == "parent_id" and "parent_id" in payload.model_fields_set}

    if "parent_id" in update and update["parent_id"]:
        if update["parent_id"] == category_id:
            raise HTTPException(status_code=400, detail="A category cannot be its own parent")
        parent = await db.categories.find_one({"id": update["parent_id"]}, {"_id": 0})
        if not parent:
            raise HTTPException(status_code=400, detail="Parent category not found")
        if parent.get("parent_id"):
            raise HTTPException(status_code=400, detail="Sub-categories cannot themselves have parents (one level deep)")

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
    # Detach children first so they don't dangle.
    await db.categories.update_many({"parent_id": category_id}, {"$set": {"parent_id": None}})
    await db.categories.delete_one({"id": category_id})
    await db.transactions.update_many({"category_id": category_id}, {"$set": {"category_id": None}})
    await db.rules.delete_many({"category_id": category_id})
    await db.budgets.delete_many({"category_id": category_id})
    return {"ok": True}
