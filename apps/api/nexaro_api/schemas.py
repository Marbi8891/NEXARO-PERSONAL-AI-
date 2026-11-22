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


class ConversationRenameRequest(BaseModel):
    # El servicio normaliza espacios y vuelve a comprobar el límite (MAX_TITLE_CHARS).
    title: str = Field(min_length=1, max_length=200)


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


class PromptVariable(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    label: str | None = Field(default=None, max_length=80)
    type: str = Field(default="text", max_length=20)
    required: bool = False
    default: str | None = Field(default=None, max_length=20_000)


class PromptCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    category: str = Field(min_length=1, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=12)
    system_prompt: str = Field(default="", max_length=20_000)
    user_template: str = Field(min_length=1, max_length=20_000)
    variables: list[PromptVariable] = Field(default_factory=list, max_length=20)


class PromptUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=12)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    user_template: str | None = Field(default=None, min_length=1, max_length=20_000)
    variables: list[PromptVariable] | None = Field(default=None, max_length=20)
    changelog: str = Field(default="Cambios", max_length=200)


class PromptRenderRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict, max_length=20)


class PromptInstallRequest(BaseModel):
    catalogue_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
