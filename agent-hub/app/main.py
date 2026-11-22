import hmac
from contextlib import asynccontextmanager
from fastapi import Depends,FastAPI,Header,HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from app.config import settings
from app.ollama import ollama
from app.prompts import build_agent_prompt,ORCHESTRATOR_PROMPT
from app.registry import registry
from app.schemas import ChatRequest,ChatResponse,PlanRequest,CodingExecuteRequest
from app.coding_agent import coding_agent
@asynccontextmanager
async def lifespan(app:FastAPI):
    registry.load()
    yield
app=FastAPI(title="NEXARO Agent Hub API",version="0.2.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_credentials=False,allow_methods=["GET","POST"],allow_headers=["Content-Type","Authorization"])
def coding_agent_status()->str:
    if not settings.coding_agent_enabled: return "disabled"
    if not settings.agent_hub_api_token: return "misconfigured"
    return "enabled"
def require_coding_access(authorization:str|None=Header(default=None))->None:
    """The coding agent writes files (and optionally runs commands): it needs an explicit opt-in and a token."""
    if coding_agent_status()!="enabled":
        raise HTTPException(status_code=503,detail="Coding agent is disabled; set CODING_AGENT_ENABLED=true and AGENT_HUB_API_TOKEN")
    scheme,_,token=(authorization or "").partition(" ")
    if scheme.lower()!="bearer" or not hmac.compare_digest(token.encode(),settings.agent_hub_api_token.encode()):
        raise HTTPException(status_code=401,detail="Invalid or missing API token",headers={"WWW-Authenticate":"Bearer"})
@app.get("/health")
async def health(): return {"status":"ok","service":"nexaro-agent-hub","coding_agent":coding_agent_status(),"commands":"enabled" if settings.coding_agent_allow_commands else "disabled"}
@app.get("/api/agents")
async def list_agents(): return {"agents":registry.list_agents(),"count":len(registry.list_agents())}
@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id:str):
    agent=registry.get_agent(agent_id)
    if not agent: raise HTTPException(status_code=404,detail="Agent not found")
    return agent
@app.get("/api/models")
async def list_models():
    try: models=await ollama.list_models()
    except (httpx.HTTPError,ValueError) as exc: raise HTTPException(status_code=502,detail=f"Ollama unavailable: {type(exc).__name__}") from exc
    return {"models":models}
@app.post("/api/agents/{agent_id}/chat",response_model=ChatResponse)
async def agent_chat(agent_id:str,request:ChatRequest):
    agent=registry.get_agent(agent_id)
    if not agent: raise HTTPException(status_code=404,detail="Agent not found")
    if not agent.get("enabled",False): raise HTTPException(status_code=403,detail="Agent is disabled")
    model=request.model or agent.get("model") or settings.ollama_default_model
    if request.context and len(request.context)>settings.max_context_chars: raise HTTPException(status_code=413,detail="Context exceeds configured limit")
    try:
        answer=await ollama.chat(model=model,system=build_agent_prompt(agent),message=request.message,context=request.context,temperature=request.temperature)
    except httpx.HTTPStatusError as exc: raise HTTPException(status_code=502,detail="Ollama returned an error") from exc
    except httpx.HTTPError as exc: raise HTTPException(status_code=502,detail="Unable to reach Ollama") from exc
    return ChatResponse(agent_id=agent_id,model=model,response=answer)
@app.post("/api/coding/execute",dependencies=[Depends(require_coding_access)])
async def coding_execute(request:CodingExecuteRequest):
    try: return await coding_agent.execute(task=request.task,model=request.model,max_iterations=request.max_iterations)
    except httpx.HTTPError as exc: raise HTTPException(status_code=502,detail="Unable to reach Ollama") from exc
@app.post("/api/orchestrator/plan")
async def orchestrator_plan(request:PlanRequest):
    agent=registry.get_agent("orchestrator")
    if not agent or not agent.get("enabled",False): raise HTTPException(status_code=503,detail="Orchestrator agent is not enabled")
    enabled=[a for a in registry.list_agents() if a.get("enabled") and a["id"]!="orchestrator"]
    roster="\n".join(f"- {a['id']}: {a['name']} ({a['category']})" for a in enabled)
    try:
        result=await ollama.chat(model=request.model or agent.get("model") or settings.ollama_default_model,system=ORCHESTRATOR_PROMPT,message=request.task,context="Available agents:\n"+roster,temperature=0.2)
    except httpx.HTTPError as exc: raise HTTPException(status_code=502,detail="Unable to reach Ollama") from exc
    return {"plan":result,"execution_status":"planning_only","delegation_performed":False}
