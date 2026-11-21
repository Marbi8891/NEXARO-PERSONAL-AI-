from pydantic import BaseModel, Field, ConfigDict
class ChatRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    message:str=Field(min_length=1,max_length=12000)
    context:str|None=Field(default=None,max_length=20000)
    model:str|None=Field(default=None,max_length=120)
    temperature:float|None=Field(default=None,ge=0,le=2)
class ChatResponse(BaseModel):
    agent_id:str
    model:str
    response:str
class PlanRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    task:str=Field(min_length=1,max_length=8000)
    model:str|None=Field(default=None,max_length=120)
class CodingExecuteRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    task:str=Field(min_length=1,max_length=8000)
    model:str|None=Field(default=None,max_length=120)
    max_iterations:int|None=Field(default=None,ge=1,le=30)
