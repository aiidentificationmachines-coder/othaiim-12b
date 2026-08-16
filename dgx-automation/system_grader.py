#!/usr/bin/env python3
"""
================================================================================
system_grader.py — Commercial Grade Assessment for Othaiim-12B
================================================================================

Grades the Othaiim-12B system across 7 pillars of commercial readiness:

  1. Model Intelligence     — Does the model give correct, coherent, useful answers?
  2. Tool Execution         — Can the agent call tools and use results correctly?
  3. Code Generation        — Does the builder produce valid, working multi-file code?
  4. Knowledge Base         — RAG quality, entity awareness, factual grounding
  5. Communication          — Response quality, tone, clarity, formatting
  6. Memory                 — Context retention, session continuity, entity persistence
  7. Deployment             — Uptime, latency, health checks, restart capability

Each pillar is scored 0-100. Target: A grade (90+ overall).
Generates improvement roadmap for any pillar below 80.

Usage:
    python3 system_grader.py --cycle-id 20260816_160000 --output-dir ~/othaiim-12b/automation/grades
    python3 system_grader.py --check

Requirements:
    pip install requests
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr); sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

class GraderConfig:
    OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    AGENT_PORT = int(os.environ.get("AGENT_PORT", "8878"))
    BUILDER_PORT = int(os.environ.get("BUILDER_PORT", "8891"))
    BASE44_PORT = int(os.environ.get("BASE44_PORT", "8890"))
    FILE_SERVER_PORT = int(os.environ.get("FILE_SERVER_PORT", "8882"))

    CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen2.5:7b")
    CODER_MODEL = os.environ.get("CODER_MODEL", "qwen2.5-coder:7b")
    LIGHT_MODEL = os.environ.get("LIGHT_MODEL", "qwen2.5:3b")
    HEAVY_MODEL = os.environ.get("HEAVY_MODEL", "gpt-oss:120b")
    EMBED_MODEL = os.environ.get("EMBED_MODEL", "embeddinggemma")

    # Grading thresholds
    GRADE_A = 90
    GRADE_B = 80
    GRADE_C = 70
    GRADE_D = 60

    # Test timeouts
    REQUEST_TIMEOUT = 60
    LONG_TIMEOUT = 300

    # OTHAIIM_HOME
    OTHAIIM_HOME = Path(os.environ.get("OTHAIIM_HOME", str(Path.home() / "othaiim-12b")))


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PillarScore:
    name: str
    score: int = 0
    grade: str = "F"
    tests: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class GradeReport:
    cycle_id: str = ""
    timestamp: str = ""
    pillars: Dict[str, PillarScore] = field(default_factory=dict)
    overall_score: int = 0
    overall_grade: str = "F"
    improvement_roadmap: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "overall_score": self.overall_score,
            "overall_grade": self.overall_grade,
            "pillars": {k: asdict(v) for k, v in self.pillars.items()},
            "improvement_roadmap": self.improvement_roadmap,
            "summary": self.summary,
        }


# ============================================================================
# Grading Helper
# ============================================================================

def score_to_grade(score: int) -> str:
    if score >= GraderConfig.GRADE_A: return "A"
    if score >= GraderConfig.GRADE_B: return "B"
    if score >= GraderConfig.GRADE_C: return "C"
    if score >= GraderConfig.GRADE_D: return "D"
    return "F"


def http_get(url: str, timeout: int = None) -> Tuple[int, Optional[dict]]:
    timeout = timeout or GraderConfig.REQUEST_TIMEOUT
    try:
        resp = requests.get(url, timeout=timeout)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {"text": resp.text[:500]}
    except requests.exceptions.Timeout:
        return 0, {"error": "timeout"}
    except Exception as e:
        return 0, {"error": str(e)}


def http_post(url: str, json_body: dict, timeout: int = None) -> Tuple[int, Optional[dict]]:
    timeout = timeout or GraderConfig.REQUEST_TIMEOUT
    try:
        resp = requests.post(url, json=json_body, timeout=timeout)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {"text": resp.text[:500]}
    except requests.exceptions.Timeout:
        return 0, {"error": "timeout"}
    except Exception as e:
        return 0, {"error": str(e)}


def ollama_generate(model: str, prompt: str, system: str = "",
                    temperature: float = 0.3) -> Optional[str]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 4096}
    }
    if system:
        payload["system"] = system
    try:
        resp = requests.post(f"{GraderConfig.OLLAMA_HOST}/api/generate",
                             json=payload, timeout=GraderConfig.LONG_TIMEOUT)
        if resp.status_code == 200:
            return resp.json().get("response", "")
    except Exception:
        pass
    return None


def measure_latency(func, *args, **kwargs) -> Tuple[Any, float]:
    t0 = time.time()
    result = func(*args, **kwargs)
    return result, time.time() - t0


# ============================================================================
# Pillar 1: Model Intelligence
# ============================================================================

def grade_model_intelligence(config: GraderConfig) -> PillarScore:
    """Test model coherence, correctness, and reasoning ability."""
    pillar = PillarScore(name="Model Intelligence")
    scores = []

    # Test 1: Basic Q&A accuracy
    test_qa = [
        ("What is 15 * 23?", "345", "math"),
        ("What is the capital of France?", "Paris", "knowledge"),
        ("Write a Python function to reverse a string.", "def reverse", "code"),
        ("Explain what a REST API is in 2 sentences.", "REST", "explanation"),
        ("What does HTTP status 404 mean?", "Not Found", "knowledge"),
    ]

    correct = 0
    for question, expected_keyword, category in test_qa:
        response = ollama_generate(config.CHAT_MODEL, question)
        test_result = {
            "test": f"QA: {question}",
            "category": category,
            "expected": expected_keyword,
            "got": response[:200] if response else "NO RESPONSE",
            "passed": False
        }
        if response and expected_keyword.lower() in response.lower():
            test_result["passed"] = True
            correct += 1
        pillar.tests.append(test_result)

    qa_score = int((correct / len(test_qa)) * 100)
    scores.append(qa_score)
    pillar.findings.append(f"Q&A accuracy: {correct}/{len(test_qa)} correct ({qa_score}%)")

    # Test 2: Reasoning (multi-step)
    reasoning_response = ollama_generate(
        config.CHAT_MODEL,
        "If a train leaves Station A at 3 PM traveling at 60 mph, and another leaves "
        "Station B (200 miles away) at 4 PM traveling at 80 mph toward the first train, "
        "what time do they meet? Show your reasoning step by step."
    )
    reasoning_test = {
        "test": "Multi-step reasoning: train problem",
        "passed": False,
        "got": reasoning_response[:300] if reasoning_response else "NO RESPONSE"
    }
    # Check if response mentions correct answer (~4:30 PM or shows proper math)
    if reasoning_response:
        if any(x in reasoning_response.lower() for x in ["4:30", "4.5", "90 miles", "1.5 hours", "4:30 pm"]):
            reasoning_test["passed"] = True
            scores.append(85)
        elif "60" in reasoning_response and "80" in reasoning_response and "mph" in reasoning_response.lower():
            # Shows work but may not have correct answer
            reasoning_test["passed"] = True
            scores.append(70)
        else:
            scores.append(40)
    else:
        scores.append(0)
    pillar.tests.append(reasoning_test)

    # Test 3: Instruction following
    instruction_response = ollama_generate(
        config.CHAT_MODEL,
        "List exactly 3 fruits. Number them 1, 2, 3. Nothing else."
    )
    instruction_test = {
        "test": "Instruction following: list 3 fruits",
        "passed": False,
        "got": instruction_response[:200] if instruction_response else "NO RESPONSE"
    }
    if instruction_response:
        # Check for numbered list of ~3 items
        numbered = re.findall(r'\d+\.\s+\w+', instruction_response)
        if len(numbered) >= 3:
            instruction_test["passed"] = True
            scores.append(90)
        elif len(numbered) >= 2:
            scores.append(60)
        else:
            scores.append(30)
    else:
        scores.append(0)
    pillar.tests.append(instruction_test)

    # Test 4: Hallucination check — does it admit when it doesn't know?
    hallucination_response = ollama_generate(
        config.CHAT_MODEL,
        "What is the phone number of John Smith who lives at 123 Main St in Springfield?"
    )
    hallucination_test = {
        "test": "Hallucination resistance: unknown personal info",
        "passed": False,
        "got": hallucination_response[:200] if hallucination_response else "NO RESPONSE"
    }
    if hallucination_response:
        lower = hallucination_response.lower()
        if any(x in lower for x in ["don't know", "cannot", "can't", "not able", "don't have", "no information", "unable"]):
            hallucination_test["passed"] = True
            scores.append(85)
        elif re.search(r'\d{3}[-.]?\d{3}[-.]?\d{4}', hallucination_response):
            # Made up a phone number — bad
            scores.append(20)
        else:
            scores.append(50)
    else:
        scores.append(0)
    pillar.tests.append(hallucination_test)

    # Test 5: Code model specifically
    code_response = ollama_generate(
        config.CODER_MODEL,
        "Write a Python function called `is_palindrome` that checks if a string is a palindrome. Include type hints and a docstring.",
        system="You are an expert Python developer."
    )
    code_test = {
        "test": "Code model: palindrome function",
        "passed": False,
        "got": code_response[:300] if code_response else "NO RESPONSE"
    }
    if code_response:
        checks = [
            "def is_palindrome" in code_response,
            "def" in code_response,
            "return" in code_response,
            ":" in code_response,
        ]
        if all(checks):
            code_test["passed"] = True
            scores.append(90)
        elif sum(checks) >= 2:
            scores.append(60)
        else:
            scores.append(20)
    else:
        scores.append(0)
    pillar.tests.append(code_test)

    pillar.score = int(sum(scores) / len(scores)) if scores else 0
    pillar.grade = score_to_grade(pillar.score)

    if pillar.score < 80:
        pillar.recommendations.append("Fine-tune on more diverse QA datasets")
        pillar.recommendations.append("Increase training epochs for reasoning tasks")
        pillar.recommendations.append("Add RLHF preference data for instruction following")

    return pillar


# ============================================================================
# Pillar 2: Tool Execution
# ============================================================================

def grade_tool_execution(config: GraderConfig) -> PillarScore:
    """Test the agent's ability to call tools and use results."""
    pillar = PillarScore(name="Tool Execution")
    scores = []

    # Test 1: Agent is reachable
    status, body = http_get(f"http://localhost:{config.AGENT_PORT}/")
    test1 = {"test": "Agent endpoint reachable", "passed": status > 0}
    scores.append(100 if status > 0 else 0)
    pillar.tests.append(test1)
    pillar.findings.append(f"Agent endpoint: HTTP {status}" if status > 0 else "Agent endpoint: unreachable")

    # Test 2: Agent can process a tool-calling prompt
    agent_response = None
    try:
        status, body = http_post(
            f"http://localhost:{config.AGENT_PORT}/api/chat",
            {"message": "What tools do you have available?", "session_id": "grader_test"}
        )
        agent_response = body
        test2 = {"test": "Agent responds to tool query", "passed": status == 200}
        scores.append(100 if status == 200 else 30)
    except Exception as e:
        test2 = {"test": "Agent responds to tool query", "passed": False, "error": str(e)}
        scores.append(0)
    pillar.tests.append(test2)

    # Test 3: Check if agent has tool registry
    try:
        status, body = http_get(f"http://localhost:{config.AGENT_PORT}/api/tools")
        if status == 200 and body:
            tools = body if isinstance(body, list) else body.get("tools", [])
            test3 = {"test": "Agent has tool registry", "passed": len(tools) > 0, "tool_count": len(tools)}
            scores.append(min(100, 50 + len(tools) * 10))
            pillar.findings.append(f"Tools registered: {len(tools)}")
        else:
            test3 = {"test": "Agent has tool registry", "passed": False, "status": status}
            scores.append(30)
    except Exception as e:
        test3 = {"test": "Agent has tool registry", "passed": False, "error": str(e)}
        scores.append(20)
    pillar.tests.append(test3)

    # Test 4: Base44 API as a tool source
    status, body = http_get(f"http://localhost:{config.BASE44_PORT}/api/entities")
    test4 = {"test": "Base44 API accessible as data tool", "passed": status == 200}
    scores.append(100 if status == 200 else 0)
    pillar.tests.append(test4)

    # Test 5: File server access
    status, _ = http_get(f"http://localhost:{config.FILE_SERVER_PORT}/")
    test5 = {"test": "File server accessible", "passed": status > 0}
    scores.append(80 if status > 0 else 0)
    pillar.tests.append(test5)

    # Test 6: Ollama as backend tool
    status, body = http_get(f"{config.OLLAMA_HOST}/api/tags")
    if status == 200:
        models = body.get("models", []) if body else []
        test6 = {"test": "Ollama backend accessible", "passed": True, "models": len(models)}
        scores.append(100)
    else:
        test6 = {"test": "Ollama backend accessible", "passed": False}
        scores.append(0)
    pillar.tests.append(test6)

    pillar.score = int(sum(scores) / len(scores)) if scores else 0
    pillar.grade = score_to_grade(pillar.score)

    if pillar.score < 80:
        pillar.recommendations.append("Add more tool definitions to agent registry")
        pillar.recommendations.append("Implement tool-call validation and error recovery")
        pillar.recommendations.append("Add retry logic for flaky tool endpoints")

    return pillar


# ============================================================================
# Pillar 3: Code Generation
# ============================================================================

def grade_code_generation(config: GraderConfig) -> PillarScore:
    """Test the builder's ability to generate valid multi-file projects."""
    pillar = PillarScore(name="Code Generation")
    scores = []

    # Test 1: Builder is reachable
    status, body = http_get(f"http://localhost:{config.BUILDER_PORT}/health")
    test1 = {"test": "Builder health endpoint", "passed": status == 200}
    scores.append(100 if status == 200 else 0)
    if status == 200 and body:
        pillar.findings.append(f"Builder status: {body.get('status', 'unknown')}")
    pillar.tests.append(test1)

    # Test 2: Generate a simple app
    t0 = time.time()
    status, body = http_post(
        f"http://localhost:{config.BUILDER_PORT}/build",
        {"request": "Create a simple todo list app", "refine": False, "stream": False},
        timeout=GraderConfig.LONG_TIMEOUT
    )
    gen_time = time.time() - t0

    test2 = {
        "test": "Generate todo app project",
        "passed": status == 200,
        "duration": f"{gen_time:.1f}s"
    }
    if status == 200 and body:
        file_count = body.get("file_count", 0)
        files = body.get("files", {})
        test2["file_count"] = file_count

        # Check for essential files
        essential = ["package.json", "tsconfig.json", "src/App.tsx", "index.html"]
        has_essential = sum(1 for f in essential if f in files)
        test2["essential_files"] = f"{has_essential}/{len(essential)}"

        if file_count >= 5 and has_essential >= 3:
            scores.append(90)
        elif file_count >= 3:
            scores.append(60)
        else:
            scores.append(30)

        # Check code quality
        app_code = files.get("src/App.tsx", "")
        if app_code:
            quality_checks = [
                "import" in app_code,
                "function" in app_code.lower() or "=>" in app_code,
                "export" in app_code,
                "Routes" in app_code or "return" in app_code,
            ]
            quality_score = int(sum(quality_checks) / len(quality_checks) * 100)
            test2["code_quality"] = quality_score
            scores.append(quality_score)

        if gen_time > 120:
            pillar.findings.append(f"Generation took {gen_time:.1f}s (slow)")

        pillar.findings.append(f"Generated {file_count} files in {gen_time:.1f}s")
    else:
        scores.append(0)
        scores.append(0)
        pillar.findings.append(f"Build failed: HTTP {status}")

    pillar.tests.append(test2)

    # Test 3: Multi-file structure check
    if status == 200 and body:
        files = body.get("files", {})
        file_types = set()
        for fpath in files.keys():
            ext = Path(fpath).suffix
            if ext:
                file_types.add(ext)
        test3 = {
            "test": "Multi-file project structure",
            "passed": len(file_types) >= 3,
            "file_types": list(file_types)
        }
        scores.append(100 if len(file_types) >= 4 else (70 if len(file_types) >= 3 else 40))
        pillar.tests.append(test3)

        # Test 4: TypeScript validity (basic checks)
        issues = 0
        for fpath, content in files.items():
            if fpath.endswith((".ts", ".tsx")):
                # Check for unbalanced braces
                open_braces = content.count("{")
                close_braces = content.count("}")
                if abs(open_braces - close_braces) > 1:
                    issues += 1
                # Check for missing exports in component files
                if "component" in fpath.lower() or "pages" in fpath:
                    if "export" not in content:
                        issues += 1

        test4 = {
            "test": "TypeScript structure validity",
            "passed": issues == 0,
            "issues": issues
        }
        scores.append(100 if issues == 0 else max(0, 100 - issues * 20))
        pillar.tests.append(test4)
    else:
        scores.extend([0, 0])

    # Test 5: Coder model can generate valid Python
    py_response = ollama_generate(
        config.CODER_MODEL,
        "Write a complete Python class called 'TaskManager' with add_task, complete_task, "
        "and list_tasks methods. Include proper docstrings and type hints.",
        system="You are an expert Python developer."
    )
    test5 = {"test": "Python code generation quality", "passed": False}
    if py_response:
        checks = [
            "class TaskManager" in py_response,
            "def add_task" in py_response,
            "def complete_task" in py_response,
            "def list_tasks" in py_response,
            "->" in py_response,  # type hints
            '"""' in py_response or "'''" in py_response,  # docstrings
        ]
        quality = sum(checks)
        test5["checks_passed"] = f"{quality}/{len(checks)}"
        test5["passed"] = quality >= 4
        scores.append(int(quality / len(checks) * 100))
    else:
        scores.append(0)
    pillar.tests.append(test5)

    # Test 6: Tailwind CSS usage in generated code
    if status == 200 and body:
        files = body.get("files", {})
        tailwind_count = 0
        for fpath, content in files.items():
            if fpath.endswith((".tsx", ".jsx", ".html")):
                if any(cls in content for cls in ["className=", "class=", "bg-", "flex", "p-4", "rounded"]):
                    tailwind_count += 1
        test6 = {
            "test": "Tailwind CSS usage",
            "passed": tailwind_count > 0,
            "files_with_tailwind": tailwind_count
        }
        scores.append(min(100, tailwind_count * 25))
        pillar.tests.append(test6)
    else:
        scores.append(0)

    pillar.score = int(sum(scores) / len(scores)) if scores else 0
    pillar.grade = score_to_grade(pillar.score)

    if pillar.score < 80:
        pillar.recommendations.append("Increase LoRA training data for code tasks")
        pillar.recommendations.append("Add more component templates to library")
        pillar.recommendations.append("Implement TypeScript compiler validation in build pipeline")
        pillar.recommendations.append("Add unit test generation for produced code")

    return pillar


# ============================================================================
# Pillar 4: Knowledge Base
# ============================================================================

def grade_knowledge_base(config: GraderConfig) -> PillarScore:
    """Test RAG quality, entity awareness, and factual grounding."""
    pillar = PillarScore(name="Knowledge Base")
    scores = []

    # Test 1: Base44 API has entities
    status, body = http_get(f"http://localhost:{config.BASE44_PORT}/api/entities")
    entity_count = 0
    if status == 200 and body:
        if isinstance(body, list):
            entity_count = len(body)
        elif isinstance(body, dict):
            entity_count = len(body.get("entities", body.get("items", [])))
    test1 = {"test": "Entities available in Base44", "passed": entity_count > 0, "count": entity_count}
    scores.append(min(100, entity_count * 20))
    pillar.findings.append(f"Entities in Base44: {entity_count}")
    pillar.tests.append(test1)

    # Test 2: RAG index exists
    rag_dir = config.OTHAIIM_HOME / "rag_db"
    rag_file = rag_dir / "rag_store.json"
    doc_count = 0
    if rag_file.exists():
        try:
            docs = json.loads(rag_file.read_text())
            doc_count = len(docs)
        except Exception:
            pass
    test2 = {"test": "RAG index exists", "passed": doc_count > 0, "documents": doc_count}
    scores.append(min(100, doc_count * 5))
    pillar.findings.append(f"RAG documents: {doc_count}")
    pillar.tests.append(test2)

    # Test 3: Embedding model works
    try:
        status, body = http_post(
            f"{config.OLLAMA_HOST}/api/embeddings",
            {"model": config.EMBED_MODEL, "prompt": "test embedding"}
        )
        test3 = {"test": "Embedding model functional", "passed": status == 200}
        if status == 200 and body:
            embedding = body.get("embedding", [])
            test3["embedding_dim"] = len(embedding)
            scores.append(100 if len(embedding) > 0 else 0)
        else:
            scores.append(0)
    except Exception as e:
        test3 = {"test": "Embedding model functional", "passed": False, "error": str(e)}
        scores.append(0)
    pillar.tests.append(test3)

    # Test 4: Entity-aware responses
    # Ask the agent a question that should reference stored entities
    if entity_count > 0:
        agent_status, agent_body = http_post(
            f"http://localhost:{config.AGENT_PORT}/api/chat",
            {"message": "What entities do you have access to?", "session_id": "grader_kb"}
        )
        test4 = {"test": "Entity-aware response", "passed": False}
        if agent_status == 200 and agent_body:
            response_text = json.dumps(agent_body).lower()
            # Check if response mentions any entity names
            if any(word in response_text for word in ["entity", "entities", "data", "database", "table"]):
                test4["passed"] = True
                scores.append(80)
            else:
                scores.append(40)
        else:
            scores.append(20)
    else:
        test4 = {"test": "Entity-aware response", "passed": False, "note": "No entities to test"}
        scores.append(0)
    pillar.tests.append(test4)

    # Test 5: Component library exists
    comp_dir = config.OTHAIIM_HOME / "component_library" / "components"
    comp_count = 0
    if comp_dir.exists():
        comp_count = len(list(comp_dir.glob("*.tsx")))
    test5 = {"test": "Component library available", "passed": comp_count > 0, "components": comp_count}
    scores.append(min(100, comp_count * 15))
    pillar.findings.append(f"Components in library: {comp_count}")
    pillar.tests.append(test5)

    # Test 6: Factual knowledge test
    fact_questions = [
        ("What programming language is Django written in?", "python"),
        ("What does API stand for?", "application programming interface"),
        ("What is HTTP?", "hypertext transfer protocol"),
    ]
    fact_correct = 0
    for question, expected in fact_questions:
        response = ollama_generate(config.CHAT_MODEL, question)
        if response and expected.lower() in response.lower():
            fact_correct += 1
    test6 = {"test": "Factual knowledge accuracy", "passed": fact_correct >= 2, "correct": f"{fact_correct}/{len(fact_questions)}"}
    scores.append(int(fact_correct / len(fact_questions) * 100))
    pillar.tests.append(test6)

    pillar.score = int(sum(scores) / len(scores)) if scores else 0
    pillar.grade = score_to_grade(pillar.score)

    if pillar.score < 80:
        pillar.recommendations.append("Rebuild RAG index with more diverse data sources")
        pillar.recommendations.append("Add domain-specific knowledge to training corpus")
        pillar.recommendations.append("Increase entity count and field richness")
        pillar.recommendations.append("Add web search capability for real-time knowledge")

    return pillar


# ============================================================================
# Pillar 5: Communication
# ============================================================================

def grade_communication(config: GraderConfig) -> PillarScore:
    """Test response quality, tone, clarity, and formatting."""
    pillar = PillarScore(name="Communication")
    scores = []

    # Test 1: Response coherence
    response = ollama_generate(
        config.CHAT_MODEL,
        "Explain the concept of recursion in programming. Keep it under 200 words."
    )
    test1 = {"test": "Response coherence (recursion explanation)", "passed": False}
    if response:
        words = len(response.split())
        has_structure = any(x in response.lower() for x in ["recursion", "function", "call", "base case"])
        reasonable_length = 20 < words < 500
        test1["word_count"] = words
        test1["has_structure"] = has_structure
        test1["reasonable_length"] = reasonable_length
        test1["passed"] = has_structure and reasonable_length
        if has_structure and reasonable_length:
            scores.append(90)
        elif has_structure:
            scores.append(60)
        else:
            scores.append(30)
    else:
        scores.append(0)
    pillar.tests.append(test1)

    # Test 2: Formatting (markdown/structured output)
    response2 = ollama_generate(
        config.CHAT_MODEL,
        "List 5 best practices for REST API design. Use bullet points or numbered lists."
    )
    test2 = {"test": "Formatted output (REST API best practices)", "passed": False}
    if response2:
        has_list = bool(re.search(r'^\s*[\d]+[\.\)]\s|^\s*[-*]\s', response2, re.MULTILINE))
        has_content = any(x in response2.lower() for x in ["api", "rest", "http", "endpoint", "status"])
        test2["has_list"] = has_list
        test2["has_content"] = has_content
        test2["passed"] = has_list and has_content
        scores.append(90 if has_list and has_content else (50 if has_content else 20))
    else:
        scores.append(0)
    pillar.tests.append(test2)

    # Test 3: Tone and professionalism
    response3 = ollama_generate(
        config.CHAT_MODEL,
        "I'm frustrated because my code keeps throwing a null pointer exception. Help me debug."
    )
    test3 = {"test": "Professional tone in frustrating scenario", "passed": False}
    if response3:
        helpful = any(x in response3.lower() for x in ["null", "none", "check", "debug", "error", "fix", "try"])
        professional = not any(x in response3.lower() for x in ["stupid", "obviously", "you should have", "rtfm"])
        test3["helpful"] = helpful
        test3["professional"] = professional
        test3["passed"] = helpful and professional
        scores.append(90 if helpful and professional else (50 if helpful else 20))
    else:
        scores.append(0)
    pillar.tests.append(test3)

    # Test 4: Conciseness
    response4 = ollama_generate(
        config.CHAT_MODEL,
        "What is a variable? Answer in exactly one sentence."
    )
    test4 = {"test": "Conciseness (one sentence answer)", "passed": False}
    if response4:
        sentences = response4.strip().split(".")
        non_empty = [s for s in sentences if s.strip()]
        test4["sentence_count"] = len(non_empty)
        test4["passed"] = len(non_empty) <= 2
        scores.append(100 if len(non_empty) <= 2 else (60 if len(non_empty) <= 3 else 30))
    else:
        scores.append(0)
    pillar.tests.append(test4)

    # Test 5: Multi-language/format awareness
    response5 = ollama_generate(
        config.CHAT_MODEL,
        "Respond to this customer: 'Can I get a quote for a custom website?' Be professional and ask for more details."
    )
    test5 = {"test": "Customer-facing communication", "passed": False}
    if response5:
        asks_for_details = any(x in response5.lower() for x in ["could you", "please", "what", "how many", "details", "requirements", "tell me"])
        professional = any(x in response5.lower() for x in ["thank", "happy to", "certainly", "of course", "help", "glad"])
        test5["asks_for_details"] = asks_for_details
        test5["professional"] = professional
        test5["passed"] = asks_for_details and professional
        scores.append(90 if asks_for_details and professional else (50 if asks_for_details or professional else 20))
    else:
        scores.append(0)
    pillar.tests.append(test5)

    # Test 6: Agent endpoint communication
    status, body = http_post(
        f"http://localhost:{config.AGENT_PORT}/api/chat",
        {"message": "Hello, can you help me?", "session_id": "grader_comm"}
    )
    test6 = {"test": "Agent communication endpoint", "passed": status == 200}
    if status == 200 and body:
        agent_response = body.get("response", body.get("message", body.get("content", "")))
        if agent_response and len(str(agent_response)) > 10:
            test6["response_preview"] = str(agent_response)[:100]
            scores.append(90)
        else:
            test6["note"] = "Response too short"
            scores.append(40)
    else:
        scores.append(0)
    pillar.tests.append(test6)

    pillar.score = int(sum(scores) / len(scores)) if scores else 0
    pillar.grade = score_to_grade(pillar.score)

    if pillar.score < 80:
        pillar.recommendations.append("Add communication quality examples to training data")
        pillar.recommendations.append("Implement response length control in system prompt")
        pillar.recommendations.append("Add tone calibration based on user sentiment")
        pillar.recommendations.append("Train on professional customer service transcripts")

    return pillar


# ============================================================================
# Pillar 6: Memory
# ============================================================================

def grade_memory(config: GraderConfig) -> PillarScore:
    """Test context retention, session continuity, and persistence."""
    pillar = PillarScore(name="Memory")
    scores = []

    # Test 1: Session continuity — can agent remember across turns?
    session_id = f"grader_memory_{int(time.time())}"

    # First message: tell the agent something
    status1, body1 = http_post(
        f"http://localhost:{config.AGENT_PORT}/api/chat",
        {"message": "Remember that my favorite color is blue and my name is TestUser.", "session_id": session_id}
    )
    test1 = {"test": "Agent accepts context (first turn)", "passed": status1 == 200}
    scores.append(80 if status1 == 200 else 0)
    pillar.tests.append(test1)

    # Second message: ask what it remembers
    status2, body2 = http_post(
        f"http://localhost:{config.AGENT_PORT}/api/chat",
        {"message": "What is my favorite color and what is my name?", "session_id": session_id}
    )
    test2 = {"test": "Agent recalls context (second turn)", "passed": False}
    if status2 == 200 and body2:
        response_text = json.dumps(body2).lower()
        remembers_color = "blue" in response_text
        remembers_name = "testuser" in response_text or "test user" in response_text or "test" in response_text
        if remembers_color and remembers_name:
            test2["passed"] = True
            scores.append(100)
        elif remembers_color or remembers_name:
            test2["partial"] = True
            scores.append(60)
        else:
            scores.append(20)
        test2["remembers_color"] = remembers_color
        test2["remembers_name"] = remembers_name
    else:
        scores.append(0)
    pillar.tests.append(test2)

    # Test 3: Entity persistence
    status, body = http_get(f"http://localhost:{config.BASE44_PORT}/api/entities")
    has_persistence = False
    if status == 200 and body:
        entities = body if isinstance(body, list) else body.get("entities", body.get("items", []))
        has_persistence = len(entities) > 0
    test3 = {"test": "Entity persistence in Base44", "passed": has_persistence}
    scores.append(80 if has_persistence else 0)
    pillar.tests.append(test3)

    # Test 4: Conversation history storage
    conv_dir = config.OTHAIIM_HOME / "data" / "conversations"
    has_conv_storage = conv_dir.exists() and any(conv_dir.iterdir()) if conv_dir.exists() else False
    # Also check if Base44 stores ChatMessage entities
    status, body = http_get(f"http://localhost:{config.BASE44_PORT}/api/entities/ChatMessage?limit=5")
    has_chat_storage = status == 200 and body and (
        len(body) > 0 if isinstance(body, list) else len(body.get("items", [])) > 0
    )
    test4 = {"test": "Conversation history storage", "passed": has_conv_storage or has_chat_storage}
    scores.append(80 if (has_conv_storage or has_chat_storage) else 30)
    pillar.tests.append(test4)

    # Test 5: Long context handling
    long_context = "Here are some facts: " + ". ".join([
        f"Fact {i}: The value of item {i} is {i * 10}"
        for i in range(1, 21)
    ])
    response = ollama_generate(
        config.CHAT_MODEL,
        f"{long_context}\n\nWhat is the value of item 15?",
        num_ctx=4096
    )
    test5 = {"test": "Long context handling (20 facts)", "passed": False}
    if response and "150" in response:
        test5["passed"] = True
        scores.append(90)
    elif response and "15" in response:
        scores.append(50)
    else:
        scores.append(10)
    pillar.tests.append(test5)

    # Test 6: Model context window size
    # Check available context length
    try:
        status, body = http_get(f"{config.OLLAMA_HOST}/api/show", timeout=10)
        # Try model-specific show
        resp = requests.post(f"{config.OLLAMA_HOST}/api/show",
                             json={"name": config.CHAT_MODEL}, timeout=10)
        if resp.status_code == 200:
            model_info = resp.json()
            context_len = model_info.get("model_info", {}).get("general.context_length", 0)
            if context_len == 0:
                # Try other paths
                params = model_info.get("parameters", {})
                context_len = params.get("num_ctx", 4096)
            test6 = {"test": "Model context window", "passed": context_len >= 4096, "context_length": context_len}
            scores.append(100 if context_len >= 8192 else (80 if context_len >= 4096 else 40))
        else:
            test6 = {"test": "Model context window", "passed": False, "note": "Could not query model info"}
            scores.append(50)  # Assume default
    except Exception as e:
        test6 = {"test": "Model context window", "passed": False, "error": str(e)}
        scores.append(50)
    pillar.tests.append(test6)

    pillar.score = int(sum(scores) / len(scores)) if scores else 0
    pillar.grade = score_to_grade(pillar.score)

    if pillar.score < 80:
        pillar.recommendations.append("Implement persistent conversation memory in Base44")
        pillar.recommendations.append("Add user preference storage and retrieval")
        pillar.recommendations.append("Increase model context window if possible")
        pillar.recommendations.append("Add summarization for long conversations")

    return pillar


# ============================================================================
# Pillar 7: Deployment
# ============================================================================

def grade_deployment(config: GraderConfig) -> PillarScore:
    """Test uptime, latency, health checks, and restart capability."""
    pillar = PillarScore(name="Deployment")
    scores = []

    # Test 1: All services are up
    services = [
        ("Agent", config.AGENT_PORT),
        ("Builder", config.BUILDER_PORT),
        ("Base44 API", config.BASE44_PORT),
        ("File Server", config.FILE_SERVER_PORT),
        ("Ollama", 11434),
    ]
    services_up = 0
    for name, port in services:
        try:
            status, _ = http_get(f"http://localhost:{port}/", timeout=5)
            if status > 0:
                services_up += 1
        except Exception:
            pass
    test1 = {"test": "All services running", "passed": services_up == len(services), "up": f"{services_up}/{len(services)}"}
    scores.append(int(services_up / len(services) * 100))
    pillar.findings.append(f"Services up: {services_up}/{len(services)}")
    pillar.tests.append(test1)

    # Test 2: Health endpoints
    health_endpoints = [
        f"http://localhost:{config.BUILDER_PORT}/health",
        f"{config.OLLAMA_HOST}/api/tags",
    ]
    health_ok = 0
    for url in health_endpoints:
        try:
            status, _ = http_get(url, timeout=5)
            if status in (200, 404):  # 404 is ok, means server is running
                health_ok += 1
        except Exception:
            pass
    test2 = {"test": "Health check endpoints", "passed": health_ok == len(health_endpoints), "ok": f"{health_ok}/{len(health_endpoints)}"}
    scores.append(int(health_ok / len(health_endpoints) * 100))
    pillar.tests.append(test2)

    # Test 3: Response latency
    latencies = []
    for _ in range(3):
        result, latency = measure_latency(
            ollama_generate, config.CHAT_MODEL, "Say hello.", temperature=0.1
        )
        latencies.append(latency)
    avg_latency = sum(latencies) / len(latencies)
    test3 = {"test": "Response latency", "passed": avg_latency < 10, "avg_latency": f"{avg_latency:.2f}s"}
    if avg_latency < 2:
        scores.append(100)
    elif avg_latency < 5:
        scores.append(85)
    elif avg_latency < 10:
        scores.append(70)
    elif avg_latency < 30:
        scores.append(50)
    else:
        scores.append(20)
    pillar.findings.append(f"Average latency: {avg_latency:.2f}s")
    pillar.tests.append(test3)

    # Test 4: Process management — is there a process manager?
    has_pm = False
    for pm in ["systemd", "supervisor", "pm2", "docker"]:
        try:
            result = subprocess.run(["which", pm], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                has_pm = True
                pillar.findings.append(f"Process manager found: {pm}")
                break
        except Exception:
            pass
    test4 = {"test": "Process manager available", "passed": has_pm}
    scores.append(80 if has_pm else 30)
    pillar.tests.append(test4)

    # Test 5: Auto-restart scripts exist
    auto_dir = config.OTHAIIM_HOME / "automation"
    scripts = ["dgx_automation_framework.sh", "auto_train_cycle.sh"]
    scripts_exist = sum(1 for s in scripts if (auto_dir / s).exists())
    test5 = {"test": "Automation scripts present", "passed": scripts_exist == len(scripts), "found": f"{scripts_exist}/{len(scripts)}"}
    scores.append(int(scripts_exist / len(scripts) * 100))
    pillar.tests.append(test5)

    # Test 6: Disk space
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 5:
                usage_str = parts[4].replace("%", "")
                usage = int(usage_str) if usage_str.isdigit() else 0
                test6 = {"test": "Disk space available", "passed": usage < 85, "usage": f"{usage}%"}
                if usage < 50:
                    scores.append(100)
                elif usage < 70:
                    scores.append(85)
                elif usage < 85:
                    scores.append(65)
                else:
                    scores.append(30)
            else:
                test6 = {"test": "Disk space available", "passed": False, "note": "Could not parse df output"}
                scores.append(50)
        else:
            test6 = {"test": "Disk space available", "passed": False}
            scores.append(50)
    except Exception as e:
        test6 = {"test": "Disk space available", "passed": False, "error": str(e)}
        scores.append(50)
    pillar.tests.append(test6)

    # Test 7: Memory availability
    try:
        result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            # Parse available memory
            parts = lines[1].split()
            if len(parts) >= 4:
                total_mem = int(parts[1])
                avail_mem = int(parts[6]) if len(parts) > 6 else int(parts[3])
                avail_pct = (avail_mem / total_mem) * 100 if total_mem > 0 else 0
                test7 = {"test": "Memory availability", "passed": avail_pct > 20, "available": f"{avail_mem}MB ({avail_pct:.0f}%)"}
                if avail_pct > 50:
                    scores.append(100)
                elif avail_pct > 20:
                    scores.append(75)
                else:
                    scores.append(30)
            else:
                test7 = {"test": "Memory availability", "passed": False}
                scores.append(50)
        else:
            test7 = {"test": "Memory availability", "passed": False}
            scores.append(50)
    except Exception as e:
        test7 = {"test": "Memory availability", "passed": False, "error": str(e)}
        scores.append(50)
    pillar.tests.append(test7)

    # Test 8: Git repository health
    try:
        os.chdir(str(config.OTHAIIM_HOME))
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5)
        uncommitted = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
        test8 = {"test": "Git repository health", "passed": uncommitted < 50, "uncommitted_files": uncommitted}
        scores.append(100 if uncommitted == 0 else (70 if uncommitted < 50 else 40))
    except Exception as e:
        test8 = {"test": "Git repository health", "passed": False, "error": str(e)}
        scores.append(30)
    pillar.tests.append(test8)

    pillar.score = int(sum(scores) / len(scores)) if scores else 0
    pillar.grade = score_to_grade(pillar.score)

    if pillar.score < 80:
        pillar.recommendations.append("Set up systemd services for auto-restart on crash")
        pillar.recommendations.append("Add monitoring alerts for service downtime")
        pillar.recommendations.append("Implement health check endpoints on all services")
        pillar.recommendations.append("Clean up old model artifacts to free disk space")
        pillar.recommendations.append("Add log rotation to prevent disk fill")

    return pillar


# ============================================================================
# Main Grading Function
# ============================================================================

def generate_improvement_roadmap(report: GradeReport) -> List[str]:
    """Generate a prioritized improvement roadmap for pillars below 80."""
    roadmap = []

    # Sort pillars by score (lowest first)
    sorted_pillars = sorted(report.pillars.items(), key=lambda x: x[1].score)

    for pillar_name, pillar in sorted_pillars:
        if pillar.score < 80:
            priority = "HIGH" if pillar.score < 60 else "MEDIUM"
            roadmap.append(f"[{priority}] {pillar_name} (score: {pillar.score}/100, grade: {pillar.grade})")
            for rec in pillar.recommendations:
                roadmap.append(f"  → {rec}")

    if not roadmap:
        roadmap.append("All pillars above 80 — focus on pushing to 90+ for A grade")

    return roadmap


def generate_summary(report: GradeReport) -> str:
    """Generate a human-readable summary."""
    lines = [
        f"Overall Grade: {report.overall_grade} ({report.overall_score}/100)",
        "",
        "Pillar Breakdown:",
    ]
    for name, pillar in report.pillars.items():
        status_icon = "✓" if pillar.score >= 80 else "⚠" if pillar.score >= 60 else "✗"
        lines.append(f"  {status_icon} {pillar.name}: {pillar.score}/100 ({pillar.grade})")

    below_80 = [p.name for p in report.pillars.values() if p.score < 80]
    if below_80:
        lines.append(f"\nPillars below 80: {', '.join(below_80)}")
        lines.append("See improvement roadmap for details.")
    else:
        lines.append("\nAll pillars at 80+. Push for 90+ to reach A grade.")

    return "\n".join(lines)


def run_grader(args) -> GradeReport:
    """Run the full grading pipeline."""
    config = GraderConfig()

    # Override config from args
    if args.agent_port:
        config.AGENT_PORT = args.agent_port
    if args.builder_port:
        config.BUILDER_PORT = args.builder_port
    if args.base44_port:
        config.BASE44_PORT = args.base44_port
    if args.file_server_port:
        config.FILE_SERVER_PORT = args.file_server_port
    if args.ollama_host:
        config.OLLAMA_HOST = args.ollama_host
    if args.chat_model:
        config.CHAT_MODEL = args.chat_model
    if args.coder_model:
        config.CODER_MODEL = args.coder_model
    if args.light_model:
        config.LIGHT_MODEL = args.light_model
    if args.heavy_model:
        config.HEAVY_MODEL = args.heavy_model
    if args.embed_model:
        config.EMBED_MODEL = args.embed_model

    cycle_id = args.cycle_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else (config.OTHAIIM_HOME / "automation" / "grades")
    output_dir.mkdir(parents=True, exist_ok=True)

    report = GradeReport(
        cycle_id=cycle_id,
        timestamp=datetime.now().isoformat()
    )

    print(f"\n{'='*60}")
    print(f"  System Grader — Cycle {cycle_id}")
    print(f"  Ollama: {config.OLLAMA_HOST}")
    print(f"  Agent: localhost:{config.AGENT_PORT}")
    print(f"  Builder: localhost:{config.BUILDER_PORT}")
    print(f"{'='*60}\n")

    # Grade each pillar
    pillar_functions = [
        ("Model Intelligence", grade_model_intelligence),
        ("Tool Execution", grade_tool_execution),
        ("Code Generation", grade_code_generation),
        ("Knowledge Base", grade_knowledge_base),
        ("Communication", grade_communication),
        ("Memory", grade_memory),
        ("Deployment", grade_deployment),
    ]

    for pillar_name, func in pillar_functions:
        print(f"\n--- Grading: {pillar_name} ---")
        try:
            pillar = func(config)
            report.pillars[pillar_name] = pillar
            print(f"  Score: {pillar.score}/100 ({pillar.grade})")
            for finding in pillar.findings:
                print(f"  • {finding}")
            passed = sum(1 for t in pillar.tests if t.get("passed"))
            total = len(pillar.tests)
            print(f"  Tests: {passed}/{total} passed")
        except Exception as e:
            print(f"  ERROR grading {pillar_name}: {e}")
            report.pillars[pillar_name] = PillarScore(
                name=pillar_name, score=0, grade="F",
                findings=[f"Grading error: {e}"]
            )

    # Calculate overall score
    if report.pillars:
        # Weighted average — all pillars equal weight
        total_score = sum(p.score for p in report.pillars.values())
        report.overall_score = int(total_score / len(report.pillars))
        report.overall_grade = score_to_grade(report.overall_score)

    # Generate roadmap and summary
    report.improvement_roadmap = generate_improvement_roadmap(report)
    report.summary = generate_summary(report)

    # Save report
    report_file = output_dir / f"grade_{cycle_id}.json"
    report_file.write_text(json.dumps(report.to_dict(), indent=2))
    print(f"\nReport saved to: {report_file}")

    # Also save as latest
    latest_file = output_dir / "grade_latest.json"
    latest_file.write_text(json.dumps(report.to_dict(), indent=2))

    # Print summary
    print(f"\n{'='*60}")
    print(report.summary)
    print(f"\n{'='*60}")

    if report.improvement_roadmap:
        print("\nImprovement Roadmap:")
        for item in report.improvement_roadmap:
            print(f"  {item}")

    return report


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="System Grader — Commercial Grade Assessment for Othaiim-12B"
    )
    parser.add_argument("--cycle-id", default="", help="Cycle ID for this grading run")
    parser.add_argument("--output-dir", default="", help="Directory to save grade reports")
    parser.add_argument("--agent-port", type=int, default=0, help="Agent port")
    parser.add_argument("--builder-port", type=int, default=0, help="Builder port")
    parser.add_argument("--base44-port", type=int, default=0, help="Base44 API port")
    parser.add_argument("--file-server-port", type=int, default=0, help="File server port")
    parser.add_argument("--ollama-host", default="", help="Ollama host URL")
    parser.add_argument("--chat-model", default="", help="Chat model name")
    parser.add_argument("--coder-model", default="", help="Coder model name")
    parser.add_argument("--light-model", default="", help="Light model name")
    parser.add_argument("--heavy-model", default="", help="Heavy model name")
    parser.add_argument("--embed-model", default="", help="Embedding model name")
    parser.add_argument("--check", action="store_true", help="Quick connectivity check only")

    args = parser.parse_args()

    if args.check:
        config = GraderConfig()
        print("Quick connectivity check:")
        for name, port in [("Agent", config.AGENT_PORT), ("Builder", config.BUILDER_PORT),
                          ("Base44", config.BASE44_PORT), ("File Server", config.FILE_SERVER_PORT),
                          ("Ollama", 11434)]:
            try:
                status, _ = http_get(f"http://localhost:{port}/", timeout=5)
                print(f"  {name:15s} port {port:5d}: HTTP {status} {'✓' if status > 0 else '✗'}")
            except Exception:
                print(f"  {name:15s} port {port:5d}: UNREACHABLE ✗")
        # Check models
        try:
            status, body = http_get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
            if status == 200 and body:
                models = [m["name"] for m in body.get("models", [])]
                print(f"\nAvailable models: {models}")
        except Exception:
            print("\nCould not list models")
        return

    run_grader(args)


if __name__ == "__main__":
    main()
