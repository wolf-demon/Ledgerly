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
    parent_id: Optional[str] = None
    name: str
    type: str  # "income" or "expense"
    color: str = "#364C2E"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CategoryCreate(BaseModel):
    project_id: str
    parent_id: Optional[str] = None
    name: str
    type: str
    color: str = "#364C2E"


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[str] = None  # set to empty string "" to clear


class Transaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    bank_account_id: Optional[str] = None
    date: str  # ISO date YYYY-MM-DD
    time: Optional[str] = None  # HH:MM[:SS] or None
    description: str
    amount: float
    type: str
    category_id: Optional[str] = None
    parent_transaction_id: Optional[str] = None  # set on child split rows
    is_split: bool = False                       # set on the original parent once split
    raw_row: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransactionUpdate(BaseModel):
    category_id: Optional[str] = None
    description: Optional[str] = None
    apply_to_similar: bool = False


class SplitLine(BaseModel):
    amount: float                    # MUST share sign with the parent
    category_id: Optional[str] = None
    description: Optional[str] = None


class SplitPayload(BaseModel):
    splits: List[SplitLine]


class BankAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    color: str = "#728A66"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BankAccountCreate(BaseModel):
    project_id: str
    name: str
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    color: str = "#728A66"


class BankAccountUpdate(BaseModel):
    name: Optional[str] = None
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    color: Optional[str] = None


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


class Budget(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    category_id: str
    period: str  # "monthly" | "yearly"
    amount: float  # always stored positive
    rollover: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BudgetUpsert(BaseModel):
    project_id: str
    category_id: str
    period: str = "monthly"
    amount: float
    rollover: bool = False
