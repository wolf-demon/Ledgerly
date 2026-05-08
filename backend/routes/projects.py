"""Project endpoints + default category seeding."""
from datetime import datetime
from typing import List

from fastapi import APIRouter

from app_db import db
from models import Category, Project, ProjectCreate

router = APIRouter()


_DEFAULT_CATEGORIES = [
    ("Salary", "income", "#4B6B40"),
    ("Other Income", "income", "#728A66"),
    ("Groceries", "expense", "#D96C4E"),
    ("Rent / Mortgage", "expense", "#364C2E"),
    ("Utilities", "expense", "#D1A77E"),
    ("Transport", "expense", "#E3C8AA"),
    ("Dining", "expense", "#D96C4E"),
    ("Entertainment", "expense", "#728A66"),
    ("Shopping", "expense", "#D1A77E"),
]


@router.post("/projects", response_model=Project)
async def create_project(payload: ProjectCreate):
    proj = Project(**payload.model_dump())
    doc = proj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.projects.insert_one(doc)
    for name, t, color in _DEFAULT_CATEGORIES:
        cat = Category(project_id=proj.id, name=name, type=t, color=color)
        cdoc = cat.model_dump()
        cdoc['created_at'] = cdoc['created_at'].isoformat()
        await db.categories.insert_one(cdoc)
    return proj


@router.get("/projects", response_model=List[Project])
async def list_projects():
    docs = await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for d in docs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return docs


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    await db.projects.delete_one({"id": project_id})
    await db.categories.delete_many({"project_id": project_id})
    await db.transactions.delete_many({"project_id": project_id})
    await db.rules.delete_many({"project_id": project_id})
    await db.budgets.delete_many({"project_id": project_id})
    return {"ok": True}
