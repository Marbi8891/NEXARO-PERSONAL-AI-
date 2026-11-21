from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("NEXARO_DB_PATH", str(ROOT.parent / "data" / "nexaro.db")))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="NEXARO AI Prompt Library", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS prompts (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL, subcategory TEXT DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
          difficulty TEXT NOT NULL DEFAULT 'Beginner', prompt_type TEXT NOT NULL DEFAULT 'General',
          visibility TEXT NOT NULL DEFAULT 'private', system_prompt TEXT NOT NULL DEFAULT '',
          user_template TEXT NOT NULL, variables TEXT NOT NULL DEFAULT '[]',
          output_format TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
          version INTEGER NOT NULL DEFAULT 1, author TEXT NOT NULL DEFAULT 'Local user',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, usage_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS executions (
          id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL, prompt_version INTEGER NOT NULL,
          model TEXT NOT NULL, variables TEXT NOT NULL, rendered_prompt TEXT NOT NULL,
          result TEXT NOT NULL DEFAULT '', duration_ms INTEGER NOT NULL DEFAULT 0,
          error TEXT DEFAULT '', created_at TEXT NOT NULL,
          FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS favorites (
          prompt_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
          FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS installed_packs (
          pack_id TEXT PRIMARY KEY, installed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflows (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          nodes TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflow_executions (
          id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, input_text TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL, final_output TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, finished_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS workflow_steps (
          id INTEGER PRIMARY KEY AUTOINCREMENT, execution_id TEXT NOT NULL, step_index INTEGER NOT NULL,
          prompt_id TEXT NOT NULL, prompt_name TEXT NOT NULL, model TEXT NOT NULL,
          input_text TEXT NOT NULL DEFAULT '', output_text TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', duration_ms INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS prompt_versions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_id TEXT NOT NULL,
          version INTEGER NOT NULL, snapshot TEXT NOT NULL, changelog TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, UNIQUE(prompt_id, version),
          FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
        );
        """)
        seed(conn)
        seed_catalogue(conn)

def seed(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]:
        return
    seeds = [
      ("python-tutor","Python Tutor","Explain Python concepts and help solve exercises without skipping reasoning.","Software Development","Python",["python","learning","coding"],"Beginner","Education","You are a patient Python tutor. Explain concepts clearly, adapt to the learner's level, and avoid giving away a complete solution before explaining the approach.","Teach me {{topic}}. My level is {{level}}. Use this context or exercise: {{context}}. Respond in {{language}}.","[{\"name\":\"topic\",\"label\":\"Topic\",\"type\":\"text\",\"required\":true},{\"name\":\"level\",\"label\":\"Level\",\"type\":\"select\",\"options\":[\"Beginner\",\"Intermediate\",\"Advanced\"],\"default\":\"Beginner\"},{\"name\":\"context\",\"label\":\"Exercise or context\",\"type\":\"textarea\"},{\"name\":\"language\",\"label\":\"Language\",\"type\":\"text\",\"default\":\"Spanish\"}]","Markdown",""),
      ("code-review","Code Reviewer","Review code for correctness, maintainability, security and test coverage.","Software Development","Code Review",["review","quality","security"],"Intermediate","Act as a pragmatic senior software engineer. Review only the code supplied. Identify concrete issues, explain impact, and propose minimal fixes. Do not invent findings.","Review this code in {{language}}. Context: {{context}}\n\n\`\`\`\n{{code}}\n\`\`\`\nPrioritize: {{priorities}}","[{\"name\":\"language\",\"label\":\"Language / stack\",\"type\":\"text\",\"required\":true},{\"name\":\"context\",\"label\":\"Context\",\"type\":\"textarea\"},{\"name\":\"code\",\"label\":\"Code\",\"type\":\"textarea\",\"required\":true},{\"name\":\"priorities\",\"label\":\"Review priorities\",\"type\":\"text\",\"default\":\"Correctness, security, readability, tests\"}]","Markdown",""),
      ("api-architect","API Architect","Design a clear API contract and discuss trade-offs.","Software Development","APIs",["api","architecture","backend"],"Advanced","You are an API architect. Produce practical, consistent API designs. State assumptions and avoid adding complexity without a reason.","Design an API for {{product}}. Stack: {{stack}}. Requirements: {{requirements}}. Include endpoints, schemas, errors, auth considerations and examples.","[{\"name\":\"product\",\"label\":\"Product / feature\",\"type\":\"text\",\"required\":true},{\"name\":\"stack\",\"label\":\"Stack\",\"type\":\"text\",\"default\":\"FastAPI\"},{\"name\":\"requirements\",\"label\":\"Requirements\",\"type\":\"textarea\",\"required\":true}]","Markdown",""),
      ("debugging","Debugging Assistant","Diagnose an error from symptoms, logs and code, then propose a testable fix.","Software Development","Debugging",["debug","troubleshooting"],"Intermediate","You are a debugging specialist. Separate observed facts from hypotheses. Give a small, ordered diagnostic plan and avoid proposing unrelated rewrites.","Help diagnose this issue. Environment: {{environment}}. Expected behavior: {{expected}}. Actual behavior: {{actual}}. Logs/code: {{details}}.","[{\"name\":\"environment\",\"label\":\"Environment\",\"type\":\"text\"},{\"name\":\"expected\",\"label\":\"Expected behavior\",\"type\":\"textarea\"},{\"name\":\"actual\",\"label\":\"Actual behavior\",\"type\":\"textarea\"},{\"name\":\"details\",\"label\":\"Logs or code\",\"type\":\"textarea\",\"required\":true}]","Markdown",""),
      ("sql-tutor","SQL Tutor","Teach SQL with examples and practice questions.","Learning & Education","Tutors",["sql","database","education"],"Beginner","You are a SQL instructor. Explain the query, show a small example table, and finish with one practice exercise unless the user asks otherwise.","Teach me {{concept}} using {{database}}. My level: {{level}}. Use this example or question: {{question}}.","[{\"name\":\"concept\",\"label\":\"Concept\",\"type\":\"text\",\"required\":true},{\"name\":\"database\",\"label\":\"Database\",\"type\":\"text\",\"default\":\"SQLite\"},{\"name\":\"level\",\"label\":\"Level\",\"type\":\"select\",\"options\":[\"Beginner\",\"Intermediate\",\"Advanced\"],\"default\":\"Beginner\"},{\"name\":\"question\",\"label\":\"Question\",\"type\":\"textarea\"}]","Markdown",""),
      ("daw-mentor","DAW Mentor","Tutor for web application development coursework and projects.","Learning & Education","Learning Paths",["DAW","study","webdev"],"Beginner","You are a Spanish FP DAW mentor. Align explanations with practical web development learning. Break work into manageable steps and check understanding.","Help me with {{module}}. Topic: {{topic}}. My current understanding: {{understanding}}. Deliver: explanation, example, practice task and self-check.","[{\"name\":\"module\",\"label\":\"Module\",\"type\":\"text\",\"required\":true},{\"name\":\"topic\",\"label\":\"Topic\",\"type\":\"text\",\"required\":true},{\"name\":\"understanding\",\"label\":\"What I know so far\",\"type\":\"textarea\"}]","Markdown",""),
      ("arabic-fusha","Arabic Fusha Tutor","Teach Modern Standard Arabic vocabulary, grammar, writing and speaking.","Languages","Arabic",["arabic","fusha","language"],"Beginner","You are a Modern Standard Arabic teacher. Include Arabic script, transliteration when helpful, Spanish meaning, pronunciation notes and short practice. Correct mistakes gently and explain them.","Teach me {{topic}}. My level is {{level}}. Focus on {{skill}}. Explain in Spanish and include Arabic examples.","[{\"name\":\"topic\",\"label\":\"Topic\",\"type\":\"text\",\"required\":true},{\"name\":\"level\",\"label\":\"Level\",\"type\":\"select\",\"options\":[\"Beginner\",\"A1\",\"A2\",\"B1\",\"B2\"],\"default\":\"Beginner\"},{\"name\":\"skill\",\"label\":\"Skill\",\"type\":\"text\",\"default\":\"Speaking and writing\"}]","Markdown",""),
      ("ielts-coach","IELTS Coach","Practice IELTS tasks and receive feedback against the requested criteria.","Languages","English",["IELTS","English","exam"],"Intermediate","You are an IELTS preparation tutor. Give criterion-based feedback, distinguish estimated feedback from official scoring, and provide a revision task.","Prepare me for IELTS {{section}}. Target band: {{target}}. Task: {{task}}. My answer: {{answer}}.","[{\"name\":\"section\",\"label\":\"Section\",\"type\":\"select\",\"options\":[\"Writing Task 1\",\"Writing Task 2\",\"Speaking\",\"Reading\",\"Listening\"],\"required\":true},{\"name\":\"target\",\"label\":\"Target band\",\"type\":\"text\",\"default\":\"8.0\"},{\"name\":\"task\",\"label\":\"Task\",\"type\":\"textarea\"},{\"name\":\"answer\",\"label\":\"My answer\",\"type\":\"textarea\"}]","Markdown",""),
      ("study-planner","Study Planner","Create a realistic plan based on time, deadlines and priorities.","Productivity","Planning",["study","planning","productivity"],"Beginner","You are a study planner. Create realistic blocks, include review and breaks, and explicitly account for constraints. Avoid assuming availability not supplied.","Plan my study period. Subjects: {{subjects}}. Available time: {{time}}. Deadlines: {{deadlines}}. Constraints: {{constraints}}.","[{\"name\":\"subjects\",\"label\":\"Subjects\",\"type\":\"textarea\",\"required\":true},{\"name\":\"time\",\"label\":\"Available time\",\"type\":\"text\",\"required\":true},{\"name\":\"deadlines\",\"label\":\"Deadlines\",\"type\":\"textarea\"},{\"name\":\"constraints\",\"label\":\"Constraints\",\"type\":\"textarea\"}]","Markdown",""),
      ("job-application","Job Application Assistant","Tailor a CV summary and application letter to a specific vacancy using supplied facts.","Productivity","Career",["job","cv","application"],"Intermediate","You are a career assistant. Use only the candidate facts and vacancy information supplied. Never invent experience, qualifications or achievements. Identify gaps honestly.","Candidate profile: {{profile}}. Vacancy: {{vacancy}}. Produce an ATS-friendly CV tailoring plan and a concise cover letter in {{language}}.","[{\"name\":\"profile\",\"label\":\"Candidate profile\",\"type\":\"textarea\",\"required\":true},{\"name\":\"vacancy\",\"label\":\"Vacancy description\",\"type\":\"textarea\",\"required\":true},{\"name\":\"language\",\"label\":\"Language\",\"type\":\"text\",\"default\":\"Spanish\"}]","Markdown",""),
      ("startup-validator","Startup Validator","Assess a business idea and design low-cost validation experiments.","Business","Startup",["startup","validation","business"],"Intermediate","You are a startup analyst. Separate assumptions from evidence, avoid fabricated market statistics, and propose measurable experiments.","Evaluate this idea: {{idea}}. Customer: {{customer}}. Geography: {{market}}. Resources: {{resources}}. Provide risks and validation experiments.","[{\"name\":\"idea\",\"label\":\"Idea\",\"type\":\"textarea\",\"required\":true},{\"name\":\"customer\",\"label\":\"Target customer\",\"type\":\"text\"},{\"name\":\"market\",\"label\":\"Market / geography\",\"type\":\"text\"},{\"name\":\"resources\",\"label\":\"Budget and resources\",\"type\":\"textarea\"}]","Markdown",""),
      ("saas-pricing","SaaS Pricing Advisor","Develop pricing hypotheses, packaging and a validation plan.","Business","SaaS",["saas","pricing","product"],"Advanced","You are a SaaS pricing advisor. Treat pricing as hypotheses unless supported by data. Explain assumptions and recommend validation.","Product: {{product}}. Audience: {{audience}}. Competitors: {{competitors}}. Costs: {{costs}}. Suggest packages and validation steps.","[{\"name\":\"product\",\"label\":\"Product\",\"type\":\"textarea\",\"required\":true},{\"name\":\"audience\",\"label\":\"Audience\",\"type\":\"text\"},{\"name\":\"competitors\",\"label\":\"Competitors\",\"type\":\"textarea\"},{\"name\":\"costs\",\"label\":\"Known costs\",\"type\":\"textarea\"}]","Markdown",""),
      ("security-review","Application Security Reviewer","Review an authorized application or code sample for security issues.","Cybersecurity","Application Security",["appsec","defensive","authorized"],"Advanced","You are a defensive application security reviewer. Scope is limited to owned systems or explicitly authorized work. Analyze supplied code/configuration, describe evidence, severity rationale and safe remediation. Do not provide exploit instructions against third-party targets.","Review this authorized system. Scope: {{scope}}. Technology: {{technology}}. Code/config: {{artifact}}. Focus: {{focus}}. Report findings and remediations.","[{\"name\":\"scope\",\"label\":\"Authorization and scope\",\"type\":\"textarea\",\"required\":true},{\"name\":\"technology\",\"label\":\"Technology\",\"type\":\"text\"},{\"name\":\"artifact\",\"label\":\"Code/configuration\",\"type\":\"textarea\",\"required\":true},{\"name\":\"focus\",\"label\":\"Focus\",\"type\":\"text\",\"default\":\"OWASP risks and secure coding\"}]","Markdown",""),
      ("soc-analyst","SOC Analyst","Triage security alerts using provided evidence and identify next steps.","Cybersecurity","SOC",["soc","blue-team","incident"],"Intermediate","You are a defensive SOC analyst. Base conclusions on supplied telemetry, label uncertainty, and recommend containment only when justified. Do not invent logs or indicators.","Alert: {{alert}}. Telemetry: {{evidence}}. Environment: {{environment}}. Provide triage, hypotheses, confidence, and next investigative steps.","[{\"name\":\"alert\",\"label\":\"Alert\",\"type\":\"textarea\",\"required\":true},{\"name\":\"evidence\",\"label\":\"Evidence / logs\",\"type\":\"textarea\",\"required\":true},{\"name\":\"environment\",\"label\":\"Environment\",\"type\":\"textarea\"}]","Markdown",""),
      ("osint-report","OSINT Report Writer","Organize lawfully collected open-source information into a sourced report.","Cybersecurity","OSINT",["osint","report","research"],"Advanced","You are an OSINT report analyst. Use only lawfully obtained public or user-provided information. Clearly distinguish facts, inference and unknowns; do not facilitate stalking, doxxing or targeting.","Research question: {{question}}. Scope and lawful purpose: {{scope}}. Collected sources/data: {{data}}. Produce a structured report with limitations.","[{\"name\":\"question\",\"label\":\"Research question\",\"type\":\"textarea\",\"required\":true},{\"name\":\"scope\",\"label\":\"Scope / purpose\",\"type\":\"textarea\",\"required\":true},{\"name\":\"data\",\"label\":\"Collected data and sources\",\"type\":\"textarea\",\"required\":true}]","Markdown",""),
      ("threat-model","Threat Modeling Assistant","Create a practical threat model for an application or feature.","Cybersecurity","Security Architecture",["threat-model","security","architecture"],"Advanced","You are a threat modeling specialist. Use a defensive perspective. State assumptions and organize threats by asset, entry point, trust boundary, impact and mitigation.","System: {{system}}. Architecture: {{architecture}}. Assets: {{assets}}. Constraints: {{constraints}}. Create a threat model and prioritized mitigations.","[{\"name\":\"system\",\"label\":\"System\",\"type\":\"text\",\"required\":true},{\"name\":\"architecture\",\"label\":\"Architecture\",\"type\":\"textarea\",\"required\":true},{\"name\":\"assets\",\"label\":\"Assets\",\"type\":\"textarea\"},{\"name\":\"constraints\",\"label\":\"Constraints\",\"type\":\"textarea\"}]","Markdown",""),
      ("technical-writer","Technical Writer","Turn rough notes into clear technical documentation.","Writing & Research","Documentation",["documentation","technical-writing"],"Intermediate","You are a technical writer. Preserve technical accuracy, flag missing information, and use concise language.","Document type: {{type}}. Audience: {{audience}}. Notes: {{notes}}. Tone: {{tone}}. Structure the document with useful headings.","[{\"name\":\"type\",\"label\":\"Document type\",\"type\":\"text\"},{\"name\":\"audience\",\"label\":\"Audience\",\"type\":\"text\"},{\"name\":\"notes\",\"label\":\"Notes\",\"type\":\"textarea\",\"required\":true},{\"name\":\"tone\",\"label\":\"Tone\",\"type\":\"text\",\"default\":\"Clear and direct\"}]","Markdown",""),
      ("research-synthesizer","Research Synthesizer","Synthesize supplied sources while preserving disagreements and evidence quality.","Writing & Research","Research",["research","synthesis","sources"],"Advanced","You are a research synthesis assistant. Use only the sources provided. Cite source labels in the answer, preserve disagreement, and identify gaps. Never fabricate citations.","Question: {{question}}. Sources: {{sources}}. Desired depth: {{depth}}. Produce a synthesis, evidence table, disagreements and gaps.","[{\"name\":\"question\",\"label\":\"Question\",\"type\":\"textarea\",\"required\":true},{\"name\":\"sources\",\"label\":\"Sources\",\"type\":\"textarea\",\"required\":true},{\"name\":\"depth\",\"label\":\"Depth\",\"type\":\"select\",\"options\":[\"Brief\",\"Detailed\",\"Comprehensive\"],\"default\":\"Detailed\"}]","Markdown",""),
      ("meeting-summary","Meeting Summarizer","Extract decisions, actions, owners and unresolved questions from notes.","Productivity","Meetings",["meeting","summary","actions"],"Beginner","You are a meeting assistant. Do not infer owners or deadlines absent from notes; mark them as unassigned or unspecified.","Meeting notes: {{notes}}. Project: {{project}}. Output summary, decisions, action items, owners, deadlines and open questions.","[{\"name\":\"notes\",\"label\":\"Meeting notes\",\"type\":\"textarea\",\"required\":true},{\"name\":\"project\",\"label\":\"Project\",\"type\":\"text\"}]","Markdown",""),
      ("decision-analysis","Decision Assistant","Compare options against explicit criteria and uncertainty.","Productivity","Decision Making",["decision","analysis"],"Intermediate","You are a decision analyst. Do not choose based on hidden preferences. Make criteria and assumptions explicit, compare trade-offs, and state what additional information could change the recommendation.","Decision: {{decision}}. Options: {{options}}. Criteria: {{criteria}}. Constraints: {{constraints}}. Recommend a process and tentative option.","[{\"name\":\"decision\",\"label\":\"Decision\",\"type\":\"textarea\",\"required\":true},{\"name\":\"options\",\"label\":\"Options\",\"type\":\"textarea\",\"required\":true},{\"name\":\"criteria\",\"label\":\"Criteria\",\"type\":\"textarea\"},{\"name\":\"constraints\",\"label\":\"Constraints\",\"type\":\"textarea\"}]","Markdown",""),
      ("docker-specialist","Docker Specialist","Help design, debug and harden Docker and Compose setups.","Software Development","DevOps",["docker","devops","containers"],"Intermediate","You are a Docker specialist. Prefer reproducible Compose solutions, least privilege, explicit health checks and safe defaults. Explain commands before destructive actions.","Goal: {{goal}}. Environment: {{environment}}. Compose or Dockerfile: {{files}}. Error: {{error}}. Provide diagnosis and a tested-by-reasoning change plan.","[{\"name\":\"goal\",\"label\":\"Goal\",\"type\":\"textarea\",\"required\":true},{\"name\":\"environment\",\"label\":\"Environment\",\"type\":\"text\"},{\"name\":\"files\",\"label\":\"Configuration\",\"type\":\"textarea\"},{\"name\":\"error\",\"label\":\"Error\",\"type\":\"textarea\"}]","Markdown",""),
      ("fastapi-specialist","FastAPI Specialist","Design and troubleshoot FastAPI APIs with validation and security in mind.","Software Development","Backend",["fastapi","python","api"],"Advanced","You are a FastAPI specialist. Follow modern async patterns where appropriate, validate inputs, handle errors consistently, and discuss security implications.","Task: {{task}}. Existing code: {{code}}. Constraints: {{constraints}}. Provide solution, rationale and tests.","[{\"name\":\"task\",\"label\":\"Task\",\"type\":\"textarea\",\"required\":true},{\"name\":\"code\",\"label\":\"Existing code\",\"type\":\"textarea\"},{\"name\":\"constraints\",\"label\":\"Constraints\",\"type\":\"textarea\"}]","Markdown",""),
      ("product-manager","Product Manager","Translate a product idea into scope, user stories and acceptance criteria.","Business","Product Management",["product","requirements","roadmap"],"Intermediate","You are a product manager. Prioritize user value and delivery risk. Separate MVP scope from later enhancements and write testable acceptance criteria.","Product: {{product}}. Users: {{users}}. Problem: {{problem}}. Constraints: {{constraints}}. Create MVP scope, user stories and acceptance criteria.","[{\"name\":\"product\",\"label\":\"Product\",\"type\":\"textarea\",\"required\":true},{\"name\":\"users\",\"label\":\"Users\",\"type\":\"text\"},{\"name\":\"problem\",\"label\":\"Problem\",\"type\":\"textarea\"},{\"name\":\"constraints\",\"label\":\"Constraints\",\"type\":\"textarea\"}]","Markdown",""),
      ("flashcards","Flashcard Generator","Create useful recall cards from supplied learning material.","Learning & Education","Active Recall",["flashcards","study","recall"],"Beginner","You are an educational flashcard designer. Cards should test one idea each, avoid ambiguous answers, and preserve the source material's terminology.","Material: {{material}}. Subject: {{subject}}. Number of cards: {{count}}. Format: question, answer, optional hint.","[{\"name\":\"material\",\"label\":\"Study material\",\"type\":\"textarea\",\"required\":true},{\"name\":\"subject\",\"label\":\"Subject\",\"type\":\"text\"},{\"name\":\"count\",\"label\":\"Number\",\"type\":\"number\",\"default\":\"15\"}]","Markdown",""),
      ("quiz-generator","Quiz Generator","Create a quiz with answer key and explanations from a source.","Learning & Education","Assessment",["quiz","assessment","learning"],"Beginner","You are an assessment designer. Questions must be answerable from the provided material. Include explanations and clearly separate the answer key.","Source material: {{material}}. Topic: {{topic}}. Question count: {{count}}. Difficulty: {{difficulty}}. Question types: {{types}}.","[{\"name\":\"material\",\"label\":\"Source material\",\"type\":\"textarea\",\"required\":true},{\"name\":\"topic\",\"label\":\"Topic\",\"type\":\"text\"},{\"name\":\"count\",\"label\":\"Number\",\"type\":\"number\",\"default\":\"10\"},{\"name\":\"difficulty\",\"label\":\"Difficulty\",\"type\":\"select\",\"options\":[\"Easy\",\"Mixed\",\"Hard\"],\"default\":\"Mixed\"},{\"name\":\"types\",\"label\":\"Types\",\"type\":\"text\",\"default\":\"Multiple choice and short answer\"}]","Markdown",""),
      ("report-generator","Report Generator","Produce a structured report from provided data and findings.","Writing & Research","Reports",["report","analysis","writing"],"Intermediate","You are a report writer. Do not add unsupported facts. Label limitations, use a clear executive summary and actionable recommendations.","Report topic: {{topic}}. Audience: {{audience}}. Findings/data: {{data}}. Format: {{format}}.","[{\"name\":\"topic\",\"label\":\"Topic\",\"type\":\"text\",\"required\":true},{\"name\":\"audience\",\"label\":\"Audience\",\"type\":\"text\"},{\"name\":\"data\",\"label\":\"Findings and data\",\"type\":\"textarea\",\"required\":true},{\"name\":\"format\",\"label\":\"Format\",\"type\":\"text\",\"default\":\"Markdown\"}]","Markdown",""),
    ]
    for item in seeds:
        (id_,name,description,category,subcategory,tags,difficulty,prompt_type,system,user_template,variables,output_format,model)=item
        stamp=now()
        conn.execute("""INSERT INTO prompts(id,name,description,category,subcategory,tags,difficulty,prompt_type,visibility,system_prompt,user_template,variables,output_format,model,version,author,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,'NEXARO',?,?)""",(id_,name,description,category,subcategory,json.dumps(tags),difficulty,prompt_type,"public",system,user_template,variables,output_format,model,stamp,stamp))
        snapshot=json.dumps(dict(id=id_,name=name,system_prompt=system,user_template=user_template,variables=json.loads(variables)),ensure_ascii=False)
        conn.execute("INSERT INTO prompt_versions(prompt_id,version,snapshot,changelog,created_at) VALUES(?,?,?,?,?)",(id_,1,snapshot,"Initial seed",stamp))

def seed_catalogue(conn: sqlite3.Connection) -> None:
    """Import the curated catalogue idempotently; never overwrite user edits."""
    catalogue_path = ROOT.parent / "data" / "prompt_catalogue_100.json"
    if not catalogue_path.exists():
        return
    try:
        catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for item in catalogue.get("prompts", []):
        if conn.execute("SELECT 1 FROM prompts WHERE id=?", (item.get("id"),)).fetchone():
            continue
        stamp = now()
        variables = item.get("variables", [])
        conn.execute("""INSERT INTO prompts(id,name,description,category,subcategory,tags,difficulty,prompt_type,visibility,system_prompt,user_template,variables,output_format,model,version,author,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""", (
            item["id"], item["name"], item.get("description", ""), item["category"], item.get("subcategory", ""),
            json.dumps(item.get("tags", []), ensure_ascii=False), item.get("difficulty", "Beginner"), item.get("prompt_type", "Assistant"),
            item.get("visibility", "public"), item.get("system_prompt", ""), item["user_template"], json.dumps(variables, ensure_ascii=False),
            item.get("output_format", "Markdown"), item.get("model", ""), item.get("author", "NEXARO"), stamp, stamp
        ))
        snapshot = json.dumps(item, ensure_ascii=False)
        conn.execute("INSERT INTO prompt_versions(prompt_id,version,snapshot,changelog,created_at) VALUES(?,?,?,?,?)", (item["id"], 1, snapshot, "Initial catalogue prompt", stamp))


def pack_catalogue() -> dict[str, Any]:
    path = ROOT.parent / "data" / "prompt_packs.json"
    if not path.exists():
        return {"packs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"packs": []}


class PromptCreate(BaseModel):
    id: str | None = None
    name: str = Field(min_length=2,max_length=120)
    description: str = Field(default="",max_length=1000)
    category: str = Field(min_length=1,max_length=80)
    subcategory: str = ""
    tags: list[str] = []
    difficulty: str = "Beginner"
    prompt_type: str = "General"
    visibility: str = "private"
    system_prompt: str = ""
    user_template: str = Field(min_length=1)
    variables: list[dict[str,Any]] = []
    output_format: str = ""
    model: str = ""
    changelog: str = "Updated prompt"

class ExecuteRequest(BaseModel):
    variables: dict[str,Any] = {}
    model: str = ""
    system_prompt: str | None = None
    user_template: str | None = None

def prompt_dict(row: sqlite3.Row) -> dict[str,Any]:
    d=dict(row)
    d["tags"]=json.loads(d["tags"])
    d["variables"]=json.loads(d["variables"])
    d["favorite"]=False
    return d

def render_template(template: str, values: dict[str,Any]) -> str:
    names=set(re.findall(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}",template))
    missing=names-set(values)
    if missing:
        raise HTTPException(422,detail={"missing_variables":sorted(missing)})
    for key in names:
        template=re.sub(r"{{\s*"+re.escape(key)+r"\s*}}",str(values.get(key,"")),template)
    return template

@app.on_event("startup")
def startup() -> None:
    init_db()

@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")

@app.get("/api/health")
def health():
    return {"status":"ok","service":"prompt-library","version":"0.1.0"}

@app.get("/api/categories")
def categories():
    with db() as conn:
        rows=conn.execute("SELECT category,subcategory,COUNT(*) AS count FROM prompts GROUP BY category,subcategory ORDER BY category,subcategory").fetchall()
    return [{"category":r["category"],"subcategory":r["subcategory"],"count":r["count"]} for r in rows]

@app.get("/api/packs")
def list_packs():
    packs = pack_catalogue().get("packs", [])
    with db() as conn:
        installed = {r[0] for r in conn.execute("SELECT pack_id FROM installed_packs")}
    return [{**pack, "installed": pack["id"] in installed, "prompt_count": len(pack.get("prompt_ids", []))} for pack in packs]

@app.get("/api/packs/{pack_id}")
def get_pack(pack_id: str):
    pack = next((p for p in pack_catalogue().get("packs", []) if p.get("id") == pack_id), None)
    if not pack:
        raise HTTPException(404, "Pack not found")
    prompts = []
    for prompt_id in pack.get("prompt_ids", []):
        try:
            prompts.append(get_prompt(prompt_id))
        except HTTPException:
            continue
    with db() as conn:
        installed = conn.execute("SELECT 1 FROM installed_packs WHERE pack_id=?", (pack_id,)).fetchone() is not None
    return {**pack, "installed": installed, "prompts": prompts}

@app.post("/api/packs/{pack_id}/install")
def install_pack(pack_id: str):
    pack = next((p for p in pack_catalogue().get("packs", []) if p.get("id") == pack_id), None)
    if not pack:
        raise HTTPException(404, "Pack not found")
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO installed_packs(pack_id,installed_at) VALUES(?,?)", (pack_id, now()))
        available = [pid for pid in pack.get("prompt_ids", []) if conn.execute("SELECT 1 FROM prompts WHERE id=?", (pid,)).fetchone()]
    return {"installed": True, "pack_id": pack_id, "available_prompts": available, "missing_prompts": sorted(set(pack.get("prompt_ids", [])) - set(available))}

@app.delete("/api/packs/{pack_id}/install")
def uninstall_pack(pack_id: str):
    with db() as conn:
        cur = conn.execute("DELETE FROM installed_packs WHERE pack_id=?", (pack_id,))
    return {"installed": False, "pack_id": pack_id, "removed": bool(cur.rowcount), "note": "Prompts remain in the library; uninstall does not delete user data."}


@app.get("/api/prompts")
def list_prompts(q: str = "", category: str = "", favorite: bool = False, sort: str = "recent", limit: int = Query(100,ge=1,le=250)):
    allowed={"recent":"updated_at DESC","name":"name COLLATE NOCASE ASC","popular":"usage_count DESC","created":"created_at DESC"}
    order=allowed.get(sort,"updated_at DESC")
    clauses=[]; params=[]
    if q:
        clauses.append("(name LIKE ? OR description LIKE ? OR user_template LIKE ? OR category LIKE ? OR tags LIKE ?)")
        pattern=f"%{q}%";params += [pattern]*5
    if category:
        clauses.append("category=?");params.append(category)
    join=" JOIN favorites f ON f.prompt_id=p.id" if favorite else ""
    sql=f"SELECT p.* FROM prompts p{join}"
    if clauses: sql += " WHERE "+" AND ".join(clauses)
    sql += f" ORDER BY {order} LIMIT ?";params.append(limit)
    with db() as conn:
        rows=conn.execute(sql,params).fetchall()
        favorites={r[0] for r in conn.execute("SELECT prompt_id FROM favorites")}
    result=[]
    for row in rows:
        d=prompt_dict(row);d["favorite"]=d["id"] in favorites;result.append(d)
    return result

@app.get("/api/prompts/{prompt_id}")
def get_prompt(prompt_id: str):
    with db() as conn:
        row=conn.execute("SELECT * FROM prompts WHERE id=?",(prompt_id,)).fetchone()
        if not row: raise HTTPException(404,"Prompt not found")
        d=prompt_dict(row);d["favorite"]=conn.execute("SELECT 1 FROM favorites WHERE prompt_id=?",(prompt_id,)).fetchone() is not None
        return d

@app.post("/api/prompts")
def create_prompt(payload: PromptCreate):
    prompt_id=payload.id or str(uuid.uuid4())
    stamp=now()
    data=payload.model_dump()
    with db() as conn:
        if conn.execute("SELECT 1 FROM prompts WHERE id=?",(prompt_id,)).fetchone(): raise HTTPException(409,"Prompt ID already exists")
        conn.execute("""INSERT INTO prompts(id,name,description,category,subcategory,tags,difficulty,prompt_type,visibility,system_prompt,user_template,variables,output_format,model,version,author,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,'Local user',?,?)""",(prompt_id,data["name"],data["description"],data["category"],data["subcategory"],json.dumps(data["tags"]),data["difficulty"],data["prompt_type"],data["visibility"],data["system_prompt"],data["user_template"],json.dumps(data["variables"]),data["output_format"],data["model"],stamp,stamp))
        snap=json.dumps(data,ensure_ascii=False)
        conn.execute("INSERT INTO prompt_versions(prompt_id,version,snapshot,changelog,created_at) VALUES(?,?,?,?,?)",(prompt_id,1,snap,data["changelog"],stamp))
    return get_prompt(prompt_id)

@app.put("/api/prompts/{prompt_id}")
def update_prompt(prompt_id: str,payload: PromptCreate):
    stamp=now()
    data=payload.model_dump()
    with db() as conn:
        old=conn.execute("SELECT * FROM prompts WHERE id=?",(prompt_id,)).fetchone()
        if not old: raise HTTPException(404,"Prompt not found")
        version=old["version"]+1
        conn.execute("""UPDATE prompts SET name=?,description=?,category=?,subcategory=?,tags=?,difficulty=?,prompt_type=?,visibility=?,system_prompt=?,user_template=?,variables=?,output_format=?,model=?,version=?,updated_at=? WHERE id=?""",(data["name"],data["description"],data["category"],data["subcategory"],json.dumps(data["tags"]),data["difficulty"],data["prompt_type"],data["visibility"],data["system_prompt"],data["user_template"],json.dumps(data["variables"]),data["output_format"],data["model"],version,stamp,prompt_id))
        snap=json.dumps(data,ensure_ascii=False)
        conn.execute("INSERT INTO prompt_versions(prompt_id,version,snapshot,changelog,created_at) VALUES(?,?,?,?,?)",(prompt_id,version,snap,data["changelog"],stamp))
    return get_prompt(prompt_id)

@app.delete("/api/prompts/{prompt_id}")
def delete_prompt(prompt_id: str):
    with db() as conn:
        cur=conn.execute("DELETE FROM prompts WHERE id=?",(prompt_id,))
        if not cur.rowcount: raise HTTPException(404,"Prompt not found")
    return {"deleted":True}

@app.post("/api/prompts/{prompt_id}/duplicate")
def duplicate_prompt(prompt_id: str):
    source=get_prompt(prompt_id)
    source["id"]=str(uuid.uuid4());source["name"]=source["name"]+" (Copy)";source["visibility"]="private"
    source["changelog"]="Duplicated"
    return create_prompt(PromptCreate(**source))

@app.post("/api/prompts/{prompt_id}/favorite")
def toggle_favorite(prompt_id: str):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM prompts WHERE id=?",(prompt_id,)).fetchone(): raise HTTPException(404,"Prompt not found")
        exists=conn.execute("SELECT 1 FROM favorites WHERE prompt_id=?",(prompt_id,)).fetchone()
        if exists: conn.execute("DELETE FROM favorites WHERE prompt_id=?",(prompt_id,));favorite=False
        else: conn.execute("INSERT INTO favorites(prompt_id,created_at) VALUES(?,?)",(prompt_id,now()));favorite=True
    return {"favorite":favorite}

@app.get("/api/prompts/{prompt_id}/versions")
def versions(prompt_id: str):
    with db() as conn:
        rows=conn.execute("SELECT version,changelog,created_at,snapshot FROM prompt_versions WHERE prompt_id=? ORDER BY version DESC",(prompt_id,)).fetchall()
    return [dict(version=r["version"],changelog=r["changelog"],created_at=r["created_at"],snapshot=json.loads(r["snapshot"])) for r in rows]

# Import/export routes
@app.get("/api/prompts/{prompt_id}/export")
def export_prompt(prompt_id: str, format: str = "json"):
    p = get_prompt(prompt_id)
    if format == "markdown":
        content = f"# {p['name']}\n\n{p['description']}\n\n## System Prompt\n\n{p['system_prompt']}\n\n## User Template\n\n{p['user_template']}\n\n## Metadata\n\n- Category: {p['category']}\n- Tags: {', '.join(p['tags'])}\n- Version: {p['version']}\n\n## Variables\n\n\`\`\`json\n{json.dumps(p['variables'], ensure_ascii=False, indent=2)}\n\`\`\`"
        return {"filename": f"{p['name'].replace(' ', '-')}.md", "content": content}
    if format != "json":
        raise HTTPException(400, "format must be json or markdown")
    return {"filename": f"{p['id']}.json", "prompt": p}

@app.get("/api/prompts/export")
def export_library():
    with db() as conn:
        rows = conn.execute("SELECT * FROM prompts ORDER BY category,name").fetchall()
    return {"schema_version": "1.0", "exported_at": now(), "prompts": [prompt_dict(r) for r in rows]}

@app.post("/api/import/preview")
def import_preview(payload: dict[str, Any]):
    items = payload.get("prompts") if isinstance(payload.get("prompts"), list) else [payload.get("prompt", payload)]
    if not items or not isinstance(items, list):
        raise HTTPException(422, "No prompt records found")
    preview = []
    with db() as conn:
        for item in items:
            if not isinstance(item, dict):
                preview.append({"valid": False, "error": "Prompt must be an object"})
                continue
            name = str(item.get("name", "")).strip()
            template = str(item.get("user_template", item.get("template", ""))).strip()
            if not name or not template:
                preview.append({"valid": False, "name": name, "error": "name and user_template are required"})
                continue
            existing = conn.execute("SELECT id,name FROM prompts WHERE id=? OR name=?", (item.get("id"), name)).fetchone()
            normalized = {**item, "name": name, "category": str(item.get("category", "Imported")).strip() or "Imported", "user_template": template}
            for key, default in {"description":"","system_prompt":"","tags":[],"variables":[],"difficulty":"Beginner","prompt_type":"Assistant","visibility":"private","output_format":"Markdown","model":""}.items():
                normalized.setdefault(key, default)
            preview.append({"valid": True, "name": name, "duplicate": dict(existing) if existing else None, "prompt": normalized})
    return {"total": len(preview), "valid": sum(1 for x in preview if x.get("valid")), "items": preview}

@app.post("/api/import/prompts")
def import_prompts(payload: dict[str, Any]):
    mode = payload.get("mode", "new")
    if mode not in ("new", "update"):
        raise HTTPException(422, "mode must be new or update")
    preview = import_preview(payload)
    imported, skipped, updated = [], [], []
    for item in preview["items"]:
        if not item.get("valid"):
            skipped.append({"name": item.get("name", ""), "error": item["error"]})
            continue
        p, duplicate = item["prompt"], item.get("duplicate")
        if duplicate and mode == "new":
            skipped.append({"name": p["name"], "reason": "duplicate"})
            continue
        if duplicate and mode == "update":
            prompt_id = duplicate["id"]
            update_prompt(prompt_id, PromptCreate(**{**p, "id": prompt_id, "changelog": "Imported update"}))
            updated.append(prompt_id)
            continue
        p["id"] = str(uuid.uuid4())
        create_prompt(PromptCreate(**{**p, "changelog": "Imported prompt"}))
        imported.append(p["id"])
    return {"imported": imported, "updated": updated, "skipped": skipped}

# Prompt Builder and quality evaluation
@app.post("/api/prompt-builder")
async def prompt_builder(payload: dict[str, Any]):
    objective = str(payload.get("objective", "")).strip()
    if not objective:
        raise HTTPException(422, "objective is required")
    parts = [("Role", payload.get("role", "")), ("Context", payload.get("context", "")), ("Task", objective), ("Constraints", payload.get("constraints", "")), ("Style", payload.get("style", "")), ("Output format", payload.get("output_format", ""))]
    brief = "\n".join(f"{label}: {value}" for label, value in parts if value)
    model = payload.get("model") or DEFAULT_MODEL
    system = "You are a prompt design assistant. Create a reusable, clear prompt from the supplied brief. Do not execute the task. Return only the prompt, with dynamic {{variables}} where useful."
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{OLLAMA_URL.rstrip('/')}/api/chat", json={"model": model, "stream": False, "messages": [{"role": "system", "content": system}, {"role": "user", "content": brief}]})
            response.raise_for_status()
        return {"prompt": response.json().get("message", {}).get("content", ""), "model": model}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Ollama request failed: {exc}")

@app.post("/api/prompts/{prompt_id}/evaluate")
async def evaluate_prompt(prompt_id: str):
    p = get_prompt(prompt_id)
    rubric = "Assess clarity, specificity, context, role, task, constraints, output format, reusability and ambiguity. Return JSON: score 0-100 (subjective), findings array, recommendations array, improved_prompt string."
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{OLLAMA_URL.rstrip('/')}/api/chat", json={"model": p.get("model") or DEFAULT_MODEL, "stream": False, "format": "json", "messages": [{"role": "system", "content": rubric}, {"role": "user", "content": json.dumps({"system_prompt": p["system_prompt"], "user_template": p["user_template"], "variables": p["variables"]}, ensure_ascii=False)}]})
            response.raise_for_status()
        content = response.json().get("message", {}).get("content", "{}")
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"raw": content}
        result["subjective"] = True
        return result
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Ollama request failed: {exc}")

# Sequential Workflow MVP
@app.get("/api/workflows")
def list_workflows():
    with db() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY updated_at DESC").fetchall()
    return [dict(r, nodes=json.loads(r["nodes"])) for r in rows]

@app.post("/api/workflows")
def create_workflow(payload: dict[str, Any]):
    name = str(payload.get("name", "")).strip()
    nodes = payload.get("nodes", [])
    if not name or not isinstance(nodes, list) or len(nodes) > 20:
        raise HTTPException(422, "Name required; workflows support up to 20 steps")
    wid, stamp = str(uuid.uuid4()), now()
    with db() as conn:
        conn.execute("INSERT INTO workflows(id,name,description,nodes,created_at,updated_at) VALUES(?,?,?,?,?,?)", (wid, name, str(payload.get("description", "")), json.dumps(nodes, ensure_ascii=False), stamp, stamp))
    return get_workflow(wid)

@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Workflow not found")
    return dict(row, nodes=json.loads(row["nodes"]))

@app.put("/api/workflows/{workflow_id}")
def update_workflow(workflow_id: str, payload: dict[str, Any]):
    current = get_workflow(workflow_id)
    name = str(payload.get("name", current["name"])).strip()
    nodes = payload.get("nodes", current["nodes"])
    if not name or not isinstance(nodes, list) or len(nodes) > 20:
        raise HTTPException(422, "Invalid workflow")
    with db() as conn:
        conn.execute("UPDATE workflows SET name=?,description=?,nodes=?,updated_at=? WHERE id=?", (name, str(payload.get("description", current["description"])), json.dumps(nodes, ensure_ascii=False), now(), workflow_id))
    return get_workflow(workflow_id)

@app.delete("/api/workflows/{workflow_id}")
def delete_workflow(workflow_id: str):
    with db() as conn:
        cur = conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
    if not cur.rowcount:
        raise HTTPException(404, "Workflow not found")
    return {"deleted": True}

@app.get("/api/workflows/{workflow_id}/executions")
def workflow_execution_history(workflow_id: str):
    with db() as conn:
        rows = conn.execute("SELECT * FROM workflow_executions WHERE workflow_id=? ORDER BY created_at DESC", (workflow_id,)).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/workflow-executions/{execution_id}")
def workflow_execution_detail(execution_id: str):
    with db() as conn:
        run = conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone()
        steps = conn.execute("SELECT * FROM workflow_steps WHERE execution_id=? ORDER BY step_index", (execution_id,)).fetchall()
    if not run:
        raise HTTPException(404, "Workflow execution not found")
    return {"execution": dict(run), "steps": [dict(r) for r in steps]}

@app.post("/api/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, payload: dict[str, Any]):
    workflow = get_workflow(workflow_id)
    nodes = workflow["nodes"]
    if not nodes:
        raise HTTPException(422, "Workflow has no steps")
    run_id, started = str(uuid.uuid4()), time.perf_counter()
    input_text = str(payload.get("input", ""))
    with db() as conn:
        conn.execute("INSERT INTO workflow_executions(id,workflow_id,input_text,status,created_at) VALUES(?,?,?,?,?)", (run_id, workflow_id, input_text, "running", now()))
    previous, logs = input_text, []
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            for i, node in enumerate(nodes):
                pid = node.get("prompt_id")
                if not pid:
                    raise ValueError(f"Step {i+1} has no prompt_id")
                p = get_prompt(pid)
                values = dict(node.get("variables", {}))
                values.setdefault("workflow_input", input_text)
                values.setdefault("previous_output", previous)
                rendered = render_template(node.get("user_template") or p["user_template"], values)
                model = node.get("model") or p.get("model") or DEFAULT_MODEL
                step_started = time.perf_counter()
                response = await client.post(f"{OLLAMA_URL.rstrip('/')}/api/chat", json={"model": model, "stream": False, "messages": [{"role": "system", "content": node.get("system_prompt", p["system_prompt"])}, {"role": "user", "content": rendered}]})
                response.raise_for_status()
                output = response.json().get("message", {}).get("content", "")
                duration = int((time.perf_counter() - step_started) * 1000)
                with db() as conn:
                    conn.execute("INSERT INTO workflow_steps(execution_id,step_index,prompt_id,prompt_name,model,input_text,output_text,status,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)", (run_id, i, pid, p["name"], model, rendered, output, "completed", duration))
                    conn.execute("UPDATE prompts SET usage_count=usage_count+1 WHERE id=?", (pid,))
                logs.append({"step": i+1, "prompt_id": pid, "prompt_name": p["name"], "model": model, "output": output, "duration_ms": duration, "status": "completed"})
                previous = output
        total = int((time.perf_counter() - started) * 1000)
        with db() as conn:
            conn.execute("UPDATE workflow_executions SET status='completed',final_output=?,finished_at=? WHERE id=?", (previous, now(), run_id))
        return {"execution_id": run_id, "status": "completed", "final_output": previous, "steps": logs, "duration_ms": total}
    except Exception as exc:
        error = str(exc)
        with db() as conn:
            conn.execute("UPDATE workflow_executions SET status='failed',error=?,finished_at=? WHERE id=?", (error, now(), run_id))
            conn.execute("INSERT INTO workflow_steps(execution_id,step_index,prompt_id,prompt_name,model,input_text,output_text,status,error,duration_ms) VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, len(logs), "", "", "", "", "", "failed", error, 0))
        raise HTTPException(502, {"execution_id": run_id, "error": error, "completed_steps": logs})


@app.get("/api/executions")
def executions(limit: int = Query(50,ge=1,le=200)):
    with db() as conn:
        rows=conn.execute("SELECT e.*,p.name AS prompt_name FROM executions e JOIN prompts p ON p.id=e.prompt_id ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/prompts/{prompt_id}/execute")
async def execute_prompt(prompt_id: str, payload: ExecuteRequest):
    prompt=get_prompt(prompt_id)
    template=payload.user_template or prompt["user_template"]
    system=payload.system_prompt if payload.system_prompt is not None else prompt["system_prompt"]
    rendered=render_template(template,payload.variables)
    model=payload.model or prompt["model"] or DEFAULT_MODEL
    execution_id=str(uuid.uuid4());started=time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response=await client.post(f"{OLLAMA_URL.rstrip('/')}/api/chat",json={"model":model,"stream":False,"messages":[{"role":"system","content":system},{"role":"user","content":rendered}]})
            response.raise_for_status()
        result=response.json().get("message",{}).get("content","")
        duration=int((time.perf_counter()-started)*1000)
        with db() as conn:
            conn.execute("UPDATE prompts SET usage_count=usage_count+1 WHERE id=?",(prompt_id,))
            conn.execute("INSERT INTO executions(id,prompt_id,prompt_version,model,variables,rendered_prompt,result,duration_ms,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(execution_id,prompt_id,prompt["version"],model,json.dumps(payload.variables),rendered,result,duration,"",now()))
        return {"id":execution_id,"result":result,"duration_ms":duration,"model":model,"rendered_prompt":rendered}
    except httpx.HTTPError as exc:
        duration=int((time.perf_counter()-started)*1000)
        message=f"Ollama request failed: {exc}"
        with db() as conn:
            conn.execute("INSERT INTO executions(id,prompt_id,prompt_version,model,variables,rendered_prompt,result,duration_ms,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(execution_id,prompt_id,prompt["version"],model,json.dumps(payload.variables),rendered,"",duration,message,now()))
        raise HTTPException(502,message)

@app.delete("/api/executions/{execution_id}")
def delete_execution(execution_id: str):
    with db() as conn:
        cur=conn.execute("DELETE FROM executions WHERE id=?",(execution_id,))
    if not cur.rowcount: raise HTTPException(404,"Execution not found")
    return {"deleted":True}

@app.get("/api/models")
async def models():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r=await client.get(f"{OLLAMA_URL.rstrip('/')}/api/tags");r.raise_for_status()
        return r.json().get("models",[])
    except httpx.HTTPError:
        return []
