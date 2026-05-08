"""Pydantic models for Ledgerly."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    type: str  # "income" or "expense"
    color: str = "#364C2E"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CategoryCreate(BaseModel):
    project_id: str
    name: str
    type: str
    color: str = "#364C2E"


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    type: Optional[str] = None


class Transaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    date: str  # ISO date YYYY-MM-DD
    description: str
    amount: float  # negative = expense, positive = income
    type: str  # "income" or "expense"
    category_id: Optional[str] = None
    raw_row: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransactionUpdate(BaseModel):
    category_id: Optional[str] = None
    description: Optional[str] = None
    apply_to_similar: bool = False


class CategoryRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    pattern: str
    category_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SuggestRequest(BaseModel):
    project_id: str
    description: str
    amount: float


class UrlImportPayload(BaseModel):
    project_id: str
    url: str


class BulkSuggestPayload(BaseModel):
    project_id: str
    only_uncategorized: bool = True
    allow_create: bool = True
    max_items: int = 200


class BulkCategorizePayload(BaseModel):
    transaction_ids: List[str]
    category_id: str
    apply_to_similar: bool = False


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ai_provider: str = "emergent"          # "emergent" | "ollama" | "none"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    emergent_key: str = ""


class SettingsUpdate(BaseModel):
    ai_provider: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    emergent_key: Optional[str] = None
