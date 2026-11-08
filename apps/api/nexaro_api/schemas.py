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
