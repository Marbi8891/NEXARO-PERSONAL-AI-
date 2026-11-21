# Agent catalogue

This is a proposed catalogue, not evidence that the agents are executable. Agents load on demand and share Ollama.

## General
- General Assistant
- Personal Assistant
- Orchestrator

## Development
- Python Developer
- Java Developer
- JavaScript Developer
- TypeScript Developer
- Frontend Developer
- Backend Developer
- Full-Stack Developer
- Software Architect
- API Architect
- Code Reviewer
- Debugging Agent
- QA Engineer
- Test Automation Engineer
- Database Engineer
- DevOps Engineer
- Docker Specialist
- Cloud Engineer
- Performance Engineer
- Technical Writer

## Cybersecurity
- SOC Analyst
- Blue Team Analyst
- OSINT Investigator
- Security Auditor
- Vulnerability Analyst
- Incident Response Agent
- Application Security Agent
- Web Security Analyst
- Network Security Analyst
- Threat Intelligence Agent
- GRC Analyst
- Security Architect
- Pentest Tutor
- Detection Engineering Agent
- Malware Analysis Assistant

## AI and data
- AI Researcher
- Machine Learning Engineer
- Data Scientist
- Data Analyst
- Prompt Engineer
- LLM Engineer
- RAG Specialist
- AI Agent Architect
- AI Evaluator
- Data Engineer

## Education
- Personal Tutor
- DAW Tutor
- Python Tutor
- Java Tutor
- SQL Tutor
- JavaScript Tutor
- Git Tutor
- Exam Simulator
- Exercise Generator
- Flashcard Generator
- Study Planner
- Socratic Tutor
- Technical English Tutor

## Business
- Business Analyst
- Startup Advisor
- Market Research Agent
- Product Manager
- Marketing Strategist
- SEO Agent
- Content Writer
- Sales Assistant
- Financial Analyst
- E-commerce Consultant

## Research
- Research Agent
- Deep Research Agent
- Fact Checker
- Scientific Researcher
- Technical Researcher
- Comparative Analysis Agent
- Risk Analyst
- Report Generator

## Productivity
- Project Manager
- Task Planner
- Document Agent
- Resume Agent
- Job Search Agent
- Interview Coach
- Career Advisor
- Meeting Assistant

## Initial enabled candidates

General Assistant (chat only), Orchestrator (planning and delegation only), Python Developer (read-only code analysis), Code Reviewer (read-only review), and DAW Tutor (education only).

Research Agent remains disabled until a constrained research provider exists. Other entries should begin as disabled templates. Avoid near-identical prompts.

## Hardware profile

Use one Ollama service. Execute sequentially by default. Do not preload all agents or run every agent concurrently. Apply per-agent timeout, context/output limits and orchestration step budgets.
