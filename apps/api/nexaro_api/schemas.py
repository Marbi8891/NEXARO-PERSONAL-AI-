from datetime import date

from pydantic import BaseModel, Field

from nexaro_core.api_keys import DEFAULT_SCOPES
from products.personal_ai.prompts import AgentId, Mode


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = Field(default=None, max_length=64)
    # Opt-in: organización cuyos documentos se consultan para responder a este mensaje.
    document_organization_id: str | None = Field(default=None, max_length=64)
    # Agente especializado (ADR-0022). Sin él, `mode` (ADR-0020) elige general o tutor.
    agent: AgentId | None = None
    mode: Mode = "general"

    @property
    def agent_id(self) -> str:
        """`agent` manda; `mode` se mantiene por compatibilidad (Python Learning Dashboard)."""
        return self.agent or self.mode


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)


class AdminCreateUserRequest(RegisterRequest):
    pass


class RegistrationSettingRequest(BaseModel):
    enabled: bool


class UserActiveRequest(BaseModel):
    active: bool


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=2, max_length=63)


class MemberAddRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = Field(min_length=1, max_length=20)


class MemberRoleRequest(BaseModel):
    role: str = Field(min_length=1, max_length=20)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    scopes: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SCOPES), min_length=1, max_length=5
    )


class DocumentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=400_000)  # el servicio aplica el límite real
    source: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=100)


class DocumentAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ExpenseCreateRequest(BaseModel):
    spent_on: date
    description: str = Field(min_length=1, max_length=200)
    amount_cents: int = Field(gt=0, le=100_000_000)
    category: str = Field(min_length=1, max_length=40)
    vat_cents: int = Field(default=0, ge=0, le=100_000_000)
    vendor: str | None = Field(default=None, max_length=120)


class ExpenseUpdateRequest(BaseModel):
    spent_on: date | None = None
    description: str | None = Field(default=None, min_length=1, max_length=200)
    amount_cents: int | None = Field(default=None, gt=0, le=100_000_000)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    vat_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    vendor: str | None = Field(default=None, max_length=120)


class AgentCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=5, max_length=500)
    system_prompt: str = Field(min_length=1, max_length=12000)
    category: str = Field(default="custom", pattern="^(general|development|cybersecurity|ai_data|education|business|research|productivity|custom)$")
    model: str | None = Field(default=None, max_length=120)
    tools: list[str] = Field(default_factory=list, max_length=30)
    permissions: dict[str, object] = Field(default_factory=lambda: {"filesystem":"none","terminal":False,"network":False})
    memory: dict[str, object] = Field(default_factory=lambda: {"enabled":False,"scope":"none"})
    autonomy: str = Field(default="assisted", pattern="^(assisted|supervised|autonomous)$")
    template_id: str | None = Field(default=None, max_length=80)

    @classmethod
    def validate_safe_defaults(cls, value):
        return value


class AgentUpdateRequest(AgentCreateRequest):
    status: str = Field(default="active", pattern="^(active|disabled)$")
