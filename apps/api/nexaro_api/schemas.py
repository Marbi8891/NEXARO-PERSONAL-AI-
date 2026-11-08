from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = Field(default=None, max_length=64)


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
