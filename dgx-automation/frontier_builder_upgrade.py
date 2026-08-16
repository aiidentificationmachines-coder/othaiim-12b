#!/usr/bin/env python3
"""
================================================================================
frontier_builder_upgrade.py — Upgrades the Elite App Builder to Frontier Grade
================================================================================

Upgrades the existing Elite builder (port 8891) from single-HTML-file generation
to a frontier-grade, multi-file project generator with:

  1. Model switching: qwen2.5-coder:7b for code generation
  2. Multi-step planning: intent -> schema -> pages -> code -> review -> fix
  3. Streaming code generation with WebSocket live preview
  4. Iterative refinement: generate -> validate -> fix -> redeploy
  5. RAG over existing entities and successful apps
  6. Multi-model routing: 3b (simple), 7b-coder (code), 120b (complex)
  7. Component library: pre-installed Tailwind + component templates
  8. Multi-file project generation: package.json, tsconfig, components, routes

Usage:
    python3 frontier_builder_upgrade.py --start
    python3 frontier_builder_upgrade.py --start --port 8891 --ollama-host http://localhost:11434
    python3 frontier_builder_upgrade.py --check      # health check
    python3 frontier_builder_upgrade.py --build "create a todo app with dark mode"

Requirements:
    pip install fastapi uvicorn websockets ollama requests jinja2 pydantic
    ollama pull qwen2.5-coder:7b
    ollama pull qwen2.5:3b
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr); sys.exit(1)

try:
    import uvicorn
except ImportError:
    print("ERROR: pip install uvicorn fastapi", file=sys.stderr); sys.exit(1)

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError:
    print("ERROR: pip install fastapi pydantic", file=sys.stderr); sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

class Config:
    OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    BUILDER_PORT = int(os.environ.get("BUILDER_PORT", "8891"))
    BASE44_API = os.environ.get("BASE44_API", "http://localhost:8890")
    FILE_SERVER = os.environ.get("FILE_SERVER", "http://localhost:8882")
    AGENT_API = os.environ.get("AGENT_API", "http://localhost:8878")

    # Model routing
    MODEL_LIGHT = "qwen2.5:3b"           # simple tasks, intent detection
    MODEL_CODER = "qwen2.5-coder:7b"     # code generation
    MODEL_HEAVY = "gpt-oss:120b"         # complex reasoning, architecture
    MODEL_CHAT = "qwen2.5:7b"           # general chat / fallback
    MODEL_EMBED = "embeddinggemma"      # embeddings for RAG

    # Project generation
    PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", str(Path.home() / "othaiim-12b" / "projects")))
    COMPONENT_LIB_DIR = Path(os.environ.get("COMPONENT_LIB_DIR", str(Path.home() / "othaiim-12b" / "component_library")))

    # RAG
    RAG_DB_DIR = Path(os.environ.get("RAG_DB_DIR", str(Path.home() / "othaiim-12b" / "rag_db")))
    MAX_RAG_CONTEXT = 4000  # max chars of RAG context to inject

    # Generation limits
    MAX_REFINEMENT_ITERATIONS = 3
    MAX_CONTEXT_TOKENS = 8192
    CODEGEN_TEMPERATURE = 0.2
    PLANNING_TEMPERATURE = 0.3
    REVIEW_TEMPERATURE = 0.1

    # Streaming
    STREAM_CHUNK_SIZE = 40  # characters per websocket message


# ============================================================================
# Ollama Client
# ============================================================================

class OllamaClient:
    """Direct HTTP client for Ollama API."""

    def __init__(self, host: str = None):
        self.host = host or Config.OLLAMA_HOST
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    def generate(self, model: str, prompt: str, system: str = "",
                 temperature: float = 0.3, stream: bool = False,
                 num_ctx: int = Config.MAX_CONTEXT_TOKENS) -> dict:
        """Non-streaming generate."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            }
        }
        if system:
            payload["system"] = system
        resp = self.session.post(f"{self.host}/api/generate", json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()

    def generate_stream(self, model: str, prompt: str, system: str = "",
                        temperature: float = 0.3,
                        num_ctx: int = Config.MAX_CONTEXT_TOKENS):
        """Streaming generator yielding text chunks."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            }
        }
        if system:
            payload["system"] = system
        with self.session.post(f"{self.host}/api/generate", json=payload,
                               stream=True, timeout=600) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if chunk.get("response"):
                        yield chunk["response"]
                    if chunk.get("done"):
                        break

    def chat(self, model: str, messages: list, temperature: float = 0.3,
             num_ctx: int = Config.MAX_CONTEXT_TOKENS) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            }
        }
        resp = self.session.post(f"{self.host}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()

    def embed(self, model: str, prompt: str) -> List[float]:
        payload = {"model": model, "prompt": prompt}
        resp = self.session.post(f"{self.host}/api/embeddings", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("embedding", [])

    def list_models(self) -> List[str]:
        resp = self.session.get(f"{self.host}/api/tags", timeout=30)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

    def is_available(self) -> bool:
        try:
            r = self.session.get(f"{self.host}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False


# ============================================================================
# Multi-Model Router
# ============================================================================

class TaskComplexity(Enum):
    SIMPLE = "simple"       # quick intent, simple text, single component
    CODE = "code"            # code generation, file creation
    COMPLEX = "complex"      # multi-step reasoning, architecture, planning
    REVIEW = "review"        # code review, validation

class ModelRouter:
    """Routes tasks to the appropriate model based on complexity."""

    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama
        self._available_models: Set[str] = set()

    def refresh_models(self):
        try:
            self._available_models = set(self.ollama.list_models())
        except Exception:
            self._available_models = set()

    def _has(self, model: str) -> bool:
        if not self._available_models:
            self.refresh_models()
        return model in self._available_models or any(model in m for m in self._available_models)

    def route(self, task_type: TaskComplexity) -> str:
        """Return the best available model for the task."""
        if task_type == TaskComplexity.SIMPLE:
            return Config.MODEL_LIGHT if self._has(Config.MODEL_LIGHT) else Config.MODEL_CHAT
        elif task_type == TaskComplexity.CODE:
            return Config.MODEL_CODER if self._has(Config.MODEL_CODER) else Config.MODEL_CHAT
        elif task_type == TaskComplexity.COMPLEX:
            return Config.MODEL_HEAVY if self._has(Config.MODEL_HEAVY) else Config.MODEL_CHAT
        elif task_type == TaskComplexity.REVIEW:
            return Config.MODEL_CODER if self._has(Config.MODEL_CODER) else Config.MODEL_CHAT
        return Config.MODEL_CHAT

    def classify_complexity(self, prompt: str) -> TaskComplexity:
        """Use the light model to classify task complexity."""
        classification_prompt = f"""Classify the following user request into exactly one category. Reply with only the category name, nothing else.

Categories:
- simple: Single question, simple text task, intent detection, formatting, or small change
- code: Code generation, creating files, building components, writing functions
- complex: Multi-step reasoning, system architecture, planning, database design, multi-file coordination
- review: Code review, validation, error checking, debugging

User request: {prompt[:500]}

Category:"""
        try:
            result = self.ollama.generate(
                model=self.route(TaskComplexity.SIMPLE),
                prompt=classification_prompt,
                temperature=0.0,
                num_ctx=2048
            )
            category = result.get("response", "").strip().lower()
            mapping = {
                "simple": TaskComplexity.SIMPLE,
                "code": TaskComplexity.CODE,
                "complex": TaskComplexity.COMPLEX,
                "review": TaskComplexity.REVIEW,
            }
            return mapping.get(category, TaskComplexity.CODE)
        except Exception:
            # Heuristic fallback
            lower = prompt.lower()
            if any(w in lower for w in ["architect", "design", "plan", "system", "database schema"]):
                return TaskComplexity.COMPLEX
            if any(w in lower for w in ["review", "check", "validate", "debug", "fix error"]):
                return TaskComplexity.REVIEW
            if any(w in lower for w in ["create", "build", "generate", "code", "component", "page"]):
                return TaskComplexity.CODE
            return TaskComplexity.SIMPLE


# ============================================================================
# RAG Engine — retrieves relevant patterns from existing apps and entities
# ============================================================================

class RAGEngine:
    """Simple vector store using Ollama embeddings + cosine similarity."""

    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama
        self.documents: List[Dict[str, Any]] = []  # {"text": str, "embedding": list, "metadata": dict}
        self.db_dir = Config.RAG_DB_DIR
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db_file = self.db_dir / "rag_store.json"
        self._load()

    def _load(self):
        if self.db_file.exists():
            try:
                data = json.loads(self.db_file.read_text())
                self.documents = data
            except Exception:
                self.documents = []

    def _save(self):
        self.db_file.write_text(json.dumps(self.documents, indent=2))

    def add_document(self, text: str, metadata: dict = None):
        if not text.strip():
            return
        try:
            embedding = self.ollama.embed(Config.MODEL_EMBED, text[:2000])
            self.documents.append({
                "text": text[:5000],
                "embedding": embedding,
                "metadata": metadata or {}
            })
            self._save()
        except Exception as e:
            print(f"[RAG] Failed to embed document: {e}")

    def index_entities(self, base44_api: str = None):
        """Fetch entities from Base44 API and index them."""
        api = base44_api or Config.BASE44_API
        try:
            resp = requests.get(f"{api}/api/entities", timeout=10)
            if resp.status_code == 200:
                entities = resp.json()
                for entity in entities:
                    name = entity.get("name", "unknown")
                    fields = entity.get("fields", [])
                    desc = entity.get("description", "")
                    text = f"Entity: {name}. Description: {desc}. Fields: {json.dumps(fields)}"
                    self.add_document(text, {"type": "entity", "name": name})
        except Exception as e:
            print(f"[RAG] Could not fetch entities: {e}")

    def index_successful_apps(self, projects_dir: Path = None):
        """Index code from previously generated successful apps."""
        pdir = projects_dir or Config.PROJECTS_ROOT
        if not pdir.exists():
            return
        for project in pdir.iterdir():
            if not project.is_dir():
                continue
            readme = project / "README.md"
            if readme.exists():
                self.add_document(readme.read_text()[:3000],
                                  {"type": "app_readme", "name": project.name})
            # Index main component files
            for src_file in project.rglob("*.{tsx,jsx,ts,js,vue,py}"):
                if src_file.stat().st_size < 50000:  # skip huge files
                    try:
                        content = src_file.read_text()[:3000]
                        self.add_document(content, {
                            "type": "app_code",
                            "file": str(src_file.relative_to(project)),
                            "project": project.name
                        })
                    except Exception:
                        pass

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant documents for query."""
        if not self.documents:
            return []
        try:
            query_embedding = self.ollama.embed(Config.MODEL_EMBED, query[:2000])
        except Exception:
            return []

        scored = []
        for doc in self.documents:
            sim = self._cosine_sim(query_embedding, doc["embedding"])
            scored.append((sim, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def get_context(self, query: str, max_chars: int = None) -> str:
        """Return formatted RAG context string for injection into prompts."""
        max_chars = max_chars or Config.MAX_RAG_CONTEXT
        docs = self.search(query, top_k=5)
        if not docs:
            return ""
        parts = []
        total = 0
        for doc in docs:
            text = doc["text"][:1000]
            meta = doc.get("metadata", {})
            header = f"[{meta.get('type', 'doc')}: {meta.get('name', '')}]"
            chunk = f"{header}\n{text}\n"
            if total + len(chunk) > max_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n".join(parts)

    @staticmethod
    def _cosine_sim(a: List[float], b: List[float]) -> float:
        if len(a) != len(b) or len(a) == 0:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def rebuild_index(self):
        """Full rebuild from Base44 entities and existing projects."""
        self.documents = []
        self.index_entities()
        self.index_successful_apps()
        self._save()
        print(f"[RAG] Indexed {len(self.documents)} documents")


# ============================================================================
# Component Library — pre-installed Tailwind + reusable components
# ============================================================================

COMPONENT_TEMPLATES = {
    "Button": '''import React from "react";

interface ButtonProps {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}

const variantClasses = {
  primary: "bg-blue-600 hover:bg-blue-700 text-white",
  secondary: "bg-gray-200 hover:bg-gray-300 text-gray-900",
  danger: "bg-red-600 hover:bg-red-700 text-white",
  ghost: "bg-transparent hover:bg-gray-100 text-gray-700",
};

const sizeClasses = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-base",
  lg: "px-6 py-3 text-lg",
};

export function Button({ children, variant = "primary", size = "md", onClick, disabled, className = "" }: ButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {children}
    </button>
  );
}
''',

    "Input": '''import React from "react";

interface InputProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  error?: string;
  className?: string;
}

export function Input({ label, value, onChange, placeholder, type = "text", error, className = "" }: InputProps) {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      {label && <label className="text-sm font-medium text-gray-700">{label}</label>}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${error ? "border-red-500" : "border-gray-300"}`}
      />
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  );
}
''',

    "Card": '''import React from "react";

interface CardProps {
  children: React.ReactNode;
  title?: string;
  className?: string;
}

export function Card({ children, title, className = "" }: CardProps) {
  return (
    <div className={`bg-white rounded-xl shadow-sm border border-gray-200 p-6 ${className}`}>
      {title && <h3 className="text-lg font-semibold mb-4">{title}</h3>}
      {children}
    </div>
  );
}
''',

    "Table": '''import React from "react";

interface TableColumn<T> {
  key: keyof T;
  label: string;
  render?: (value: any, row: T) => React.ReactNode;
}

interface TableProps<T> {
  columns: TableColumn<T>[];
  data: T[];
  onRowClick?: (row: T) => void;
}

export function Table<T extends Record<string, any>>({ columns, data, onRowClick }: TableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((col) => (
              <th key={String(col.key)} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {data.map((row, i) => (
            <tr
              key={i}
              onClick={() => onRowClick?.(row)}
              className={onRowClick ? "cursor-pointer hover:bg-gray-50" : ""}
            >
              {columns.map((col) => (
                <td key={String(col.key)} className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
''',

    "Modal": '''import React, { useEffect } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
}

export function Modal({ open, onClose, title, children }: ModalProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    if (open) window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full mx-4 p-6">
        {title && <h2 className="text-xl font-semibold mb-4">{title}</h2>}
        {children}
        <button onClick={onClose} className="absolute top-4 right-4 text-gray-400 hover:text-gray-600">✕</button>
      </div>
    </div>
  );
}
''',

    "Badge": '''import React from "react";

interface BadgeProps {
  children: React.ReactNode;
  color?: "gray" | "green" | "red" | "blue" | "yellow";
}

const colorClasses = {
  gray: "bg-gray-100 text-gray-700",
  green: "bg-green-100 text-green-700",
  red: "bg-red-100 text-red-700",
  blue: "bg-blue-100 text-blue-700",
  yellow: "bg-yellow-100 text-yellow-700",
};

export function Badge({ children, color = "gray" }: BadgeProps) {
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClasses[color]}`}>{children}</span>;
}
''',

    "Navbar": '''import React from "react";

interface NavItem { label: string; href: string; }
interface NavbarProps { brand: string; items: NavItem[]; }

export function Navbar({ brand, items }: NavbarProps) {
  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
      <div className="text-xl font-bold text-gray-900">{brand}</div>
      <div className="flex gap-6">
        {items.map((item) => (
          <a key={item.href} href={item.href} className="text-gray-600 hover:text-gray-900 font-medium">{item.label}</a>
        ))}
      </div>
    </nav>
  );
}
''',

    "Sidebar": '''import React from "react";

interface SidebarItem { label: string; icon?: string; active?: boolean; onClick?: () => void; }
interface SidebarProps { items: SidebarItem[]; title?: string; }

export function Sidebar({ items, title }: SidebarProps) {
  return (
    <aside className="w-64 bg-gray-900 text-white min-h-screen p-4">
      {title && <h2 className="text-lg font-semibold mb-6 px-2">{title}</h2>}
      <nav className="space-y-1">
        {items.map((item, i) => (
          <button
            key={i}
            onClick={item.onClick}
            className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${item.active ? "bg-blue-600" : "hover:bg-gray-800"}`}
          >
            {item.icon && <span className="mr-2">{item.icon}</span>}
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
''',
}

PACKAGE_JSON_TEMPLATE = {
    "name": "",
    "version": "1.0.0",
    "private": True,
    "type": "module",
    "scripts": {
        "dev": "vite",
        "build": "tsc && vite build",
        "preview": "vite preview",
        "lint": "eslint src --ext ts,tsx"
    },
    "dependencies": {
        "react": "^18.3.0",
        "react-dom": "^18.3.0",
        "react-router-dom": "^6.22.0",
        "lucide-react": "^0.344.0",
    },
    "devDependencies": {
        "@types/react": "^18.3.0",
        "@types/react-dom": "^18.3.0",
        "@vitejs/plugin-react": "^4.2.0",
        "autoprefixer": "^10.4.18",
        "postcss": "^8.4.35",
        "tailwindcss": "^3.4.1",
        "typescript": "^5.4.0",
        "vite": "^5.2.0"
    }
}

TSCONFIG_TEMPLATE = {
    "compilerOptions": {
        "target": "ES2020",
        "useDefineForClassFields": True,
        "lib": ["ES2020", "DOM", "DOM.Iterable"],
        "module": "ESNext",
        "skipLibCheck": True,
        "moduleResolution": "bundler",
        "allowImportingTsExtensions": True,
        "resolveJsonModule": True,
        "isolatedModules": True,
        "noEmit": True,
        "jsx": "react-jsx",
        "strict": True,
        "noUnusedLocals": True,
        "noUnusedParameters": True,
        "noFallthroughCasesInSwitch": True,
    },
    "include": ["src"]
}

VITE_CONFIG_TEMPLATE = '''import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
  },
});
'''

TAILWIND_CONFIG_TEMPLATE = ''';import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
'''

POSTCSS_CONFIG_TEMPLATE = '''export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
'''

INDEX_CSS_TEMPLATE = '''@tailwind base;
@tailwind components;
@tailwind utilities;
'''

INDEX_HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{TITLE}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
'''

MAIN_TSX_TEMPLATE = '''import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
'''

APP_TSX_TEMPLATE = '''import React from "react";
import { Routes, Route } from "react-router-dom";
{IMPORTS}

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Routes>
{ROUTES}
      </Routes>
    </div>
  );
}

export default App;
'''

GITIGNORE_TEMPLATE = '''node_modules/
dist/
.env
*.log
.DS_Store
.vite/
'''


class ComponentLibrary:
    """Manages pre-installed Tailwind + component templates."""

    def __init__(self):
        self.templates = COMPONENT_TEMPLATES
        self.lib_dir = Config.COMPONENT_LIB_DIR
        self._ensure_lib_dir()

    def _ensure_lib_dir(self):
        self.lib_dir.mkdir(parents=True, exist_ok=True)
        components_dir = self.lib_dir / "components"
        components_dir.mkdir(exist_ok=True)
        for name, code in self.templates.items():
            filepath = components_dir / f"{name}.tsx"
            if not filepath.exists():
                filepath.write_text(code)

    def get_component(self, name: str) -> Optional[str]:
        return self.templates.get(name)

    def list_components(self) -> List[str]:
        return list(self.templates.keys())

    def get_component_code(self, names: List[str]) -> Dict[str, str]:
        """Return dict of component name -> code for the requested set."""
        return {n: self.templates[n] for n in names if n in self.templates}

    def install_to_project(self, project_dir: Path, components: List[str] = None):
        """Copy component files into a project's src/components/ui/ directory."""
        ui_dir = project_dir / "src" / "components" / "ui"
        ui_dir.mkdir(parents=True, exist_ok=True)
        components = components or list(self.templates.keys())
        for name in components:
            code = self.templates.get(name)
            if code:
                (ui_dir / f"{name}.tsx").write_text(code)

    def get_index_file(self, components: List[str] = None) -> str:
        """Generate an index.ts barrel file for components."""
        components = components or list(self.templates.keys())
        exports = "\n".join(f'export {{ {c} }} from "./{c}";' for c in components)
        return exports


# ============================================================================
# Multi-Step Planning Pipeline
# ============================================================================

@dataclass
class ProjectPlan:
    """Structured plan for a project generation cycle."""
    id: str = ""
    intent: str = ""
    app_name: str = ""
    description: str = ""
    entities: List[Dict[str, Any]] = field(default_factory=list)
    pages: List[Dict[str, Any]] = field(default_factory=list)
    components_needed: List[str] = field(default_factory=list)
    file_list: List[str] = field(default_factory=list)
    rag_context: str = ""
    complexity: str = "code"
    status: str = "planning"
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GenerationStep:
    step_number: int
    name: str
    model: str
    prompt: str
    response: str = ""
    duration_seconds: float = 0.0
    status: str = "pending"
    error: str = ""


class PlanningPipeline:
    """Multi-step planning: intent -> schema -> pages -> code -> review -> fix."""

    def __init__(self, ollama: OllamaClient, router: ModelRouter, rag: RAGEngine,
                 component_lib: ComponentLibrary):
        self.ollama = ollama
        self.router = router
        self.rag = rag
        self.component_lib = component_lib
        self.steps: List[GenerationStep] = []

    def _record_step(self, step: GenerationStep):
        self.steps.append(step)
        print(f"  [Step {step.step_number}] {step.name} — {step.status} ({step.duration_seconds:.1f}s)")

    def plan(self, user_request: str) -> ProjectPlan:
        """Execute the full planning pipeline and return a structured plan."""
        plan = ProjectPlan(
            id=uuid.uuid4().hex[:12],
            intent=user_request,
            created_at=datetime.now().isoformat(),
        )

        print(f"\n{'='*60}")
        print(f"Planning project for: {user_request[:100]}")
        print(f"{'='*60}")

        # Step 1: Classify complexity
        t0 = time.time()
        complexity = self.router.classify_complexity(user_request)
        plan.complexity = complexity.value
        self._record_step(GenerationStep(
            step_number=1, name="Classify Complexity",
            model=self.router.route(TaskComplexity.SIMPLE),
            prompt=f"Classify: {user_request[:200]}",
            response=complexity.value,
            duration_seconds=time.time() - t0,
            status="done"
        ))

        # Step 2: RAG retrieval
        t0 = time.time()
        rag_context = self.rag.get_context(user_request)
        plan.rag_context = rag_context
        self._record_step(GenerationStep(
            step_number=2, name="RAG Retrieval",
            model=Config.MODEL_EMBED,
            prompt=user_request[:200],
            response=f"Retrieved {len(rag_context)} chars of context",
            duration_seconds=time.time() - t0,
            status="done" if rag_context else "skipped"
        ))

        # Step 3: Understand intent & design schema (use heavy or chat model)
        t0 = time.time()
        planning_model = self.router.route(TaskComplexity.COMPLEX)
        schema_prompt = self._build_schema_prompt(user_request, rag_context)
        schema_response = self.ollama.generate(
            model=planning_model,
            prompt=schema_prompt,
            system="You are an expert software architect. Generate JSON only.",
            temperature=Config.PLANNING_TEMPERATURE
        ).get("response", "")
        self._record_step(GenerationStep(
            step_number=3, name="Design Schema",
            model=planning_model,
            prompt=schema_prompt[:200] + "...",
            response=schema_response[:200] + "...",
            duration_seconds=time.time() - t0,
            status="done"
        ))

        # Parse schema
        schema = self._parse_json(schema_response)
        if schema:
            plan.app_name = schema.get("app_name", "generated-app")
            plan.description = schema.get("description", "")
            plan.entities = schema.get("entities", [])
            plan.pages = schema.get("pages", [])
            plan.components_needed = schema.get("components_needed", [])
        else:
            # Fallback
            plan.app_name = "app_" + plan.id
            plan.entities = [{"name": "Item", "fields": [{"name": "title", "type": "string"}]}]
            plan.pages = [{"name": "Home", "route": "/", "description": "Main page"}]

        # Step 4: Plan file structure
        plan.file_list = self._plan_files(plan)
        plan.status = "planned"

        print(f"\nPlan summary:")
        print(f"  App: {plan.app_name}")
        print(f"  Entities: {len(plan.entities)}")
        print(f"  Pages: {len(plan.pages)}")
        print(f"  Files: {len(plan.file_list)}")
        print(f"  Components: {plan.components_needed}")

        return plan

    def _build_schema_prompt(self, request: str, rag_context: str) -> str:
        component_list = ", ".join(self.component_lib.list_components())
        return f"""You are designing a multi-file React + TypeScript + Tailwind web application.

User request: {request}

Available pre-built components: {component_list}

Reference context from existing apps and entities:
{rag_context if rag_context else "(none available)"}

Generate a JSON object with this exact structure:
{{
  "app_name": "kebab-case-app-name",
  "description": "Brief description of the app",
  "entities": [
    {{
      "name": "EntityName",
      "fields": [
        {{"name": "field_name", "type": "string|number|boolean|date|text", "required": true}}
      ]
    }}
  ],
  "pages": [
    {{
      "name": "PageName",
      "route": "/route-path",
      "description": "What this page does",
      "entity": "EntityName (optional, if the page is entity-centric)"
    }}
  ],
  "components_needed": ["Button", "Card", "Table", ...]
}}

Rules:
- Use kebab-case for app_name and routes
- Use PascalCase for entity names and page names
- Include only components from the available list, plus any custom ones needed
- Keep it practical and focused
- Generate valid JSON only, no markdown fences
"""

    def _parse_json(self, text: str) -> Optional[dict]:
        """Extract JSON from model response (handles code fences, extra text)."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON block
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        # Try to find the first { ... last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass
        return None

    def _plan_files(self, plan: ProjectPlan) -> List[str]:
        """Generate the list of files to create."""
        files = [
            "package.json",
            "tsconfig.json",
            "vite.config.ts",
            "tailwind.config.ts",
            "postcss.config.js",
            ".gitignore",
            "index.html",
            "src/main.tsx",
            "src/App.tsx",
            "src/index.css",
        ]
        # Component files
        for comp in plan.components_needed:
            if comp in self.component_lib.templates:
                files.append(f"src/components/ui/{comp}.tsx")
        # Page files
        for page in plan.pages:
            safe_name = page["name"]
            files.append(f"src/pages/{safe_name}.tsx")
        # Entity API files
        for entity in plan.entities:
            safe_name = entity["name"]
            files.append(f"src/api/{safe_name.lower()}Api.ts")
        # Index barrel for components
        if plan.components_needed:
            files.append("src/components/ui/index.ts")
        return files


# ============================================================================
# Code Generator — multi-file generation with streaming
# ============================================================================

class CodeGenerator:
    """Generates multi-file project code with streaming support."""

    def __init__(self, ollama: OllamaClient, router: ModelRouter,
                 component_lib: ComponentLibrary):
        self.ollama = ollama
        self.router = router
        self.component_lib = component_lib

    async def generate_project(self, plan: ProjectPlan, websocket: WebSocket = None,
                               project_dir: Path = None) -> Dict[str, str]:
        """Generate all files for a project plan. Returns dict of path -> content."""
        project_dir = project_dir or (Config.PROJECTS_ROOT / plan.app_name)
        project_dir.mkdir(parents=True, exist_ok=True)

        files: Dict[str, str] = {}
        coder_model = self.router.route(TaskComplexity.CODE)

        async def _emit(msg: dict):
            if websocket:
                try:
                    await websocket.send_json(msg)
                except Exception:
                    pass
            else:
                print(f"  [{msg.get('type', 'info')}] {msg.get('file', msg.get('message', ''))}")

        # 1. Generate scaffold files (instant, no LLM needed)
        await _emit({"type": "status", "message": "Generating scaffold files..."})

        files["package.json"] = self._gen_package_json(plan)
        files["tsconfig.json"] = json.dumps(TSCONFIG_TEMPLATE, indent=2)
        files["vite.config.ts"] = VITE_CONFIG_TEMPLATE
        files["tailwind.config.ts"] = TAILWIND_CONFIG_TEMPLATE
        files["postcss.config.js"] = POSTCSS_CONFIG_TEMPLATE
        files[".gitignore"] = GITIGNORE_TEMPLATE
        files["index.html"] = INDEX_HTML_TEMPLATE.replace("{TITLE}", plan.app_name.replace("-", " ").title())
        files["src/index.css"] = INDEX_CSS_TEMPLATE
        files["src/main.tsx"] = MAIN_TSX_TEMPLATE

        # Write scaffold immediately
        for path, content in files.items():
            fpath = project_dir / path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            await _emit({"type": "file_complete", "file": path})

        # 2. Install pre-built components
        if plan.components_needed:
            await _emit({"type": "status", "message": f"Installing {len(plan.components_needed)} components..."})
            self.component_lib.install_to_project(project_dir, plan.components_needed)
            index_content = self.component_lib.get_index_file(plan.components_needed)
            index_path = project_dir / "src" / "components" / "ui" / "index.ts"
            index_path.write_text(index_content)
            files["src/components/ui/index.ts"] = index_content
            for comp in plan.components_needed:
                await _emit({"type": "file_complete", "file": f"src/components/ui/{comp}.tsx"})

        # 3. Generate entity API files
        for entity in plan.entities:
            entity_name = entity["name"]
            await _emit({"type": "generating", "file": f"src/api/{entity_name.lower()}Api.ts"})
            api_code = self._gen_entity_api(entity, plan)
            api_path = f"src/api/{entity_name.lower()}Api.ts"
            files[api_path] = api_code
            (project_dir / api_path).parent.mkdir(parents=True, exist_ok=True)
            (project_dir / api_path).write_text(api_code)
            await _emit({"type": "file_complete", "file": api_path})

        # 4. Generate page components (with streaming)
        for page in plan.pages:
            page_name = page["name"]
            await _emit({"type": "generating", "file": f"src/pages/{page_name}.tsx"})
            page_code = await self._generate_page_code(page, plan, coder_model, websocket)
            page_path = f"src/pages/{page_name}.tsx"
            files[page_path] = page_code
            (project_dir / page_path).parent.mkdir(parents=True, exist_ok=True)
            (project_dir / page_path).write_text(page_code)
            await _emit({"type": "file_complete", "file": page_path})

        # 5. Generate App.tsx (router)
        await _emit({"type": "generating", "file": "src/App.tsx"})
        app_code = self._gen_app_tsx(plan)
        files["src/App.tsx"] = app_code
        (project_dir / "src/App.tsx").write_text(app_code)
        await _emit({"type": "file_complete", "file": "src/App.tsx"})

        # 6. Generate README
        readme = self._gen_readme(plan)
        files["README.md"] = readme
        (project_dir / "README.md").write_text(readme)

        await _emit({"type": "project_complete", "file_count": len(files), "project_dir": str(project_dir)})
        return files

    async def _generate_page_code(self, page: dict, plan: ProjectPlan,
                                  model: str, websocket: WebSocket = None) -> str:
        """Generate a single page component, with optional streaming."""
        page_name = page["name"]
        route = page.get("route", "/")
        description = page.get("description", "")
        entity = page.get("entity")

        entity_context = ""
        if entity:
            for e in plan.entities:
                if e["name"] == entity:
                    entity_context = f"Entity: {e['name']}\nFields: {json.dumps(e['fields'], indent=2)}"

        components_available = ", ".join(plan.components_needed)
        rag = plan.rag_context[:1500] if plan.rag_context else ""

        prompt = f"""Generate a complete React + TypeScript + Tailwind page component.

App: {plan.app_name}
Page: {page_name}
Route: {route}
Description: {description}

{entity_context if entity_context else ""}

Available pre-built components (import from "../components/ui"): {components_available}

Reference context:
{rag}

Requirements:
- Use functional component with React hooks
- Use Tailwind CSS for all styling
- Import pre-built components from "../components/ui" where applicable
- If this page manages entity data, include CRUD operations (create, read, update, delete)
- Use TypeScript interfaces for props and state
- Include loading states and error handling
- Make it responsive and production-ready

Generate ONLY the TypeScript file content, no markdown fences, no explanations.

```tsx
"""

        if websocket:
            # Stream via WebSocket
            full_code = ""
            await websocket.send_json({"type": "stream_start", "file": f"src/pages/{page_name}.tsx"})
            for chunk in self.ollama.generate_stream(
                model=model, prompt=prompt,
                system="You are an expert React/TypeScript developer. Generate clean, production-ready code.",
                temperature=Config.CODEGEN_TEMPERATURE
            ):
                full_code += chunk
                await websocket.send_json({
                    "type": "stream_chunk",
                    "file": f"src/pages/{page_name}.tsx",
                    "chunk": chunk
                })
            await websocket.send_json({"type": "stream_end", "file": f"src/pages/{page_name}.tsx"})
            return self._clean_code_output(full_code)
        else:
            # Non-streaming
            result = self.ollama.generate(
                model=model, prompt=prompt,
                system="You are an expert React/TypeScript developer. Generate clean, production-ready code.",
                temperature=Config.CODEGEN_TEMPERATURE
            )
            return self._clean_code_output(result.get("response", ""))

    def _clean_code_output(self, code: str) -> str:
        """Remove markdown code fences and leading/trailing whitespace."""
        code = re.sub(r'^```(?:tsx?|javascript|jsx)?\s*\n?', '', code)
        code = re.sub(r'\n?```\s*$', '', code)
        return code.strip()

    def _gen_package_json(self, plan: ProjectPlan) -> str:
        pkg = dict(PACKAGE_JSON_TEMPLATE)
        pkg["name"] = plan.app_name
        return json.dumps(pkg, indent=2)

    def _gen_entity_api(self, entity: dict, plan: ProjectPlan) -> str:
        entity_name = entity["name"]
        fields = entity.get("fields", [])
        base_url = Config.BASE44_API

        field_names = [f["name"] for f in fields]
        interface_fields = "\n".join(
            f"  {f['name']}: {self._ts_type(f.get('type', 'string'))};"
            for f in fields
        )

        return f'''// Auto-generated API client for {entity_name}
// Generated by frontier_builder_upgrade.py

export interface {entity_name} {{
{interface_fields}
  id?: string;
  created_date?: string;
  updated_date?: string;
}}

const BASE_URL = "{base_url}";

export async function list{entity_name}s(): Promise<{entity_name}[]> {{
  const res = await fetch(`${{BASE_URL}}/api/entities/{entity_name.lower()}s`);
  if (!res.ok) throw new Error(`Failed to list {entity_name}s: ${{res.statusText}}`);
  return res.json();
}}

export async function get{entity_name}(id: string): Promise<{entity_name}> {{
  const res = await fetch(`${{BASE_URL}}/api/entities/{entity_name.lower()}s/${{id}}`);
  if (!res.ok) throw new Error(`Failed to get {entity_name}: ${{res.statusText}}`);
  return res.json();
}}

export async function create{entity_name}(data: Partial<{entity_name}>): Promise<{entity_name}> {{
  const res = await fetch(`${{BASE_URL}}/api/entities/{entity_name.lower()}s`, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify(data),
  }});
  if (!res.ok) throw new Error(`Failed to create {entity_name}: ${{res.statusText}}`);
  return res.json();
}}

export async function update{entity_name}(id: string, data: Partial<{entity_name}>): Promise<{entity_name}> {{
  const res = await fetch(`${{BASE_URL}}/api/entities/{entity_name.lower()}s/${{id}}`, {{
    method: "PUT",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify(data),
  }});
  if (!res.ok) throw new Error(`Failed to update {entity_name}: ${{res.statusText}}`);
  return res.json();
}}

export async function delete{entity_name}(id: string): Promise<void> {{
  const res = await fetch(`${{BASE_URL}}/api/entities/{entity_name.lower()}s/${{id}}`, {{
    method: "DELETE",
  }});
  if (!res.ok) throw new Error(`Failed to delete {entity_name}: ${{res.statusText}}`);
}}
'''

    def _gen_app_tsx(self, plan: ProjectPlan) -> str:
        imports = []
        routes = []
        for page in plan.pages:
            page_name = page["name"]
            route = page.get("route", "/")
            imports.append(f'import {page_name} from "./pages/{page_name}";')
            routes.append(f'        <Route path="{route}" element={{<{page_name} />}} />')

        imports_str = "\n".join(imports)
        routes_str = "\n".join(routes)

        code = APP_TSX_TEMPLATE
        code = code.replace("{IMPORTS}", imports_str)
        code = code.replace("{ROUTES}", routes_str)
        return code

    def _gen_readme(self, plan: ProjectPlan) -> str:
        components_str = ", ".join(plan.components_needed) if plan.components_needed else "None"
        entities_str = "\n".join(
            f"- **{e['name']}**: {', '.join(f.get('name', '') for f in e.get('fields', []))}"
            for e in plan.entities
        ) if plan.entities else "None"
        pages_str = "\n".join(
            f"- **{p['name']}** (`{p.get('route', '/')}`): {p.get('description', '')}"
            for p in plan.pages
        ) if plan.pages else "None"

        return f'''# {plan.app_name.replace("-", " ").title()}

{plan.description}

## Getting Started

```bash
npm install
npm run dev
```

## Project Structure

### Entities
{entities_str}

### Pages
{pages_str}

### Components Used
{components_str}

## Tech Stack
- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- React Router (routing)

## Generated By
Frontier Builder Upgrade — Othaiim-12B on DGX Spark
Cycle: {plan.id}
Date: {plan.created_at}
'''


# ============================================================================
# Iterative Refinement — generate -> validate -> fix -> redeploy
# ============================================================================

class CodeValidator:
    """Validates generated code for common issues."""

    SYNTAX_PATTERNS = {
        "unclosed_brace": (r'\{[^{}]*$', "Unclosed brace"),
        "missing_semicolon": (r'(?<!;)\n\s*(?:const|let|var|import|export)\s', None),  # heuristic
    }

    @classmethod
    def validate_file(cls, filepath: str, content: str) -> List[Dict[str, str]]:
        issues = []

        # Check for empty files
        if not content.strip():
            issues.append({"severity": "error", "message": "File is empty", "line": 0})
            return issues

        # Check for unbalanced braces/parens/brackets
        for opener, closer, name in [("{", "}", "braces"), ("(", ")", "parens"), ("[", "]", "brackets")]:
            count = content.count(opener) - content.count(closer)
            if count != 0:
                # Account for strings and comments (rough heuristic)
                issues.append({
                    "severity": "warning",
                    "message": f"Unbalanced {name}: difference of {count}",
                    "line": len(content.split("\n"))
                })

        # Check for common import issues
        if filepath.endswith(".tsx") or filepath.endswith(".ts"):
            if "import React" not in content and ("React." in content or "useState" in content or "useEffect" in content):
                issues.append({
                    "severity": "error",
                    "message": "Missing React import but React APIs used",
                    "line": 1
                })

            # Check for JSX without closing tags
            unclosed = re.findall(r'<(\w+)(?:\s[^>]*)?(?<!/)>', content)
            closed = re.findall(r'</(\w+)>', content)
            self_closing = re.findall(r'<(\w+)[^>]*/>', content)
            open_tags = [t for t in unclosed if t not in ("br", "hr", "img", "input", "meta", "link", "br/", "hr/")]

            # Rough check
            for tag in open_tags:
                if tag not in closed and tag not in [sc for sc in self_closing]:
                    # Not necessarily an error (could be self-closing variant), just warn
                    pass

        # Check for placeholder text
        if "TODO" in content or "FIXME" in content or "PLACEHOLDER" in content:
            issues.append({
                "severity": "warning",
                "message": "Contains TODO/FIXME/PLACEHOLDER",
                "line": content.find("TODO") if "TODO" in content else content.find("FIXME")
            })

        return issues

    @classmethod
    def validate_project(cls, files: Dict[str, str]) -> Dict[str, List[Dict[str, str]]]:
        results = {}
        for filepath, content in files.items():
            issues = cls.validate_file(filepath, content)
            if issues:
                results[filepath] = issues
        return results


class RefinementEngine:
    """Iterative refinement: generate -> validate -> fix -> redeploy."""

    def __init__(self, ollama: OllamaClient, router: ModelRouter):
        self.ollama = ollama
        self.router = router
        self.validator = CodeValidator()

    def refine(self, files: Dict[str, str], plan: ProjectPlan,
               websocket: WebSocket = None, project_dir: Path = None) -> Tuple[Dict[str, str], List[dict]]:
        """Run iterative refinement on generated files."""
        all_fixes = []
        coder_model = self.router.route(TaskComplexity.CODE)

        for iteration in range(Config.MAX_REFINEMENT_ITERATIONS):
            print(f"\n  Refinement iteration {iteration + 1}/{Config.MAX_REFINEMENT_ITERATIONS}")

            # Validate
            issues = self.validator.validate_project(files)
            if not issues:
                print(f"  ✓ No issues found — project is clean.")
                break

            total_issues = sum(len(v) for v in issues.values())
            print(f"  Found {total_issues} issues in {len(issues)} files")

            if websocket:
                try:
                    asyncio.create_task(websocket.send_json({
                        "type": "refinement_iteration",
                        "iteration": iteration + 1,
                        "issues": total_issues
                    }))
                except Exception:
                    pass

            # Fix each file with issues
            for filepath, file_issues in issues.items():
                error_issues = [i for i in file_issues if i["severity"] == "error"]
                if not error_issues:
                    continue  # Skip warnings for now

                current_content = files.get(filepath, "")
                fix_prompt = self._build_fix_prompt(filepath, current_content, error_issues, plan)

                try:
                    result = self.ollama.generate(
                        model=coder_model,
                        prompt=fix_prompt,
                        system="You are an expert code reviewer. Fix the issues and return the corrected file only.",
                        temperature=Config.REVIEW_TEMPERATURE
                    )
                    fixed_code = result.get("response", "")

                    # Clean output
                    fixed_code = re.sub(r'^```(?:tsx?|javascript|jsx)?\s*\n?', '', fixed_code)
                    fixed_code = re.sub(r'\n?```\s*$', '', fixed_code).strip()

                    if fixed_code and len(fixed_code) > 50:
                        files[filepath] = fixed_code
                        if project_dir:
                            fpath = project_dir / filepath
                            fpath.write_text(fixed_code)
                        all_fixes.append({
                            "file": filepath,
                            "iteration": iteration + 1,
                            "issues_fixed": len(error_issues)
                        })
                        print(f"    Fixed {filepath} ({len(error_issues)} issues)")
                except Exception as e:
                    print(f"    Failed to fix {filepath}: {e}")

        return files, all_fixes

    def _build_fix_prompt(self, filepath: str, content: str,
                          issues: List[dict], plan: ProjectPlan) -> str:
        issues_str = "\n".join(f"- {i['message']} (line {i.get('line', '?')})" for i in issues)
        return f"""Review and fix the following TypeScript/React file.

File: {filepath}
Issues found:
{issues_str}

Current code:
```tsx
{content}
```

Fix all the issues listed above. Return ONLY the corrected file content, no markdown fences, no explanations.

App context: {plan.app_name} — {plan.description}
"""


# ============================================================================
# FastAPI Server with WebSocket live preview
# ============================================================================

# Pydantic models
class BuildRequest(BaseModel):
    request: str = Field(..., description="User's app description/request")
    project_name: str = Field(default="", description="Optional project name override")
    refine: bool = Field(default=True, description="Run iterative refinement")
    stream: bool = Field(default=True, description="Stream generation via WebSocket")

class BuildResponse(BaseModel):
    project_id: str
    app_name: str
    files: Dict[str, str]
    file_count: int
    plan: dict
    refinement_report: List[dict] = []
    validation_issues: Dict[str, list] = {}
    duration_seconds: float
    project_dir: str

class HealthResponse(BaseModel):
    status: str
    ollama: bool
    models: List[str]
    builder_port: int
    rag_documents: int
    components_available: List[str]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Frontier Elite Builder", version="2.0.0",
                  description="Frontier-grade multi-file app builder with live preview")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize components
    ollama = OllamaClient()
    router = ModelRouter(ollama)
    router.refresh_models()
    rag = RAGEngine(ollama)
    component_lib = ComponentLibrary()
    pipeline = PlanningPipeline(ollama, router, rag, component_lib)
    codegen = CodeGenerator(ollama, router, component_lib)
    refiner = RefinementEngine(ollama, router)

    # Static files for live preview
    Config.PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse("""<!DOCTYPE html>
<html>
<head><title>Frontier Elite Builder</title>
<style>
body { font-family: system-ui; max-width: 800px; margin: 40px auto; padding: 20px; }
h1 { color: #1a1a2e; }
code { background: #f0f0f0; padding: 2px 6px; border-radius: 4px; }
.endpoint { margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 8px; }
</style>
</head>
<body>
<h1>Frontier Elite Builder v2.0</h1>
<p>Multi-file project generation with live preview, RAG, and multi-model routing.</p>
<h2>Endpoints</h2>
<div class="endpoint"><code>GET /health</code> — Health check</div>
<div class="endpoint"><code>POST /build</code> — Build a project (returns project JSON)</div>
<div class="endpoint"><code>WS /ws/build</code> — WebSocket streaming build</div>
<div class="endpoint"><code>GET /projects</code> — List generated projects</div>
<div class="endpoint"><code>GET /projects/{name}</code> — Get project file listing</div>
<div class="endpoint"><code>GET /preview/{name}</code> — Live preview (serves project HTML)</div>
<div class="endpoint"><code>POST /rag/rebuild</code> — Rebuild RAG index</div>
</body>
</html>""")

    @app.get("/health", response_model=HealthResponse)
    async def health():
        models = ollama.list_models() if ollama.is_available() else []
        return HealthResponse(
            status="ok" if ollama.is_available() else "degraded",
            ollama=ollama.is_available(),
            models=models,
            builder_port=Config.BUILDER_PORT,
            rag_documents=len(rag.documents),
            components_available=component_lib.list_components()
        )

    @app.post("/build", response_model=BuildResponse)
    async def build(req: BuildRequest):
        t0 = time.time()
        try:
            # Plan
            plan = pipeline.plan(req.request)
            if req.project_name:
                plan.app_name = req.project_name

            # Generate
            project_dir = Config.PROJECTS_ROOT / plan.app_name
            files = await codegen.generate_project(plan, websocket=None, project_dir=project_dir)

            # Refine
            refinement_report = []
            validation_issues = {}
            if req.refine:
                files, refinement_report = refiner.refine(files, plan, websocket=None, project_dir=project_dir)
                validation_issues = CodeValidator.validate_project(files)

            plan.status = "complete"

            return BuildResponse(
                project_id=plan.id,
                app_name=plan.app_name,
                files=files,
                file_count=len(files),
                plan=plan.to_dict(),
                refinement_report=refinement_report,
                validation_issues=validation_issues,
                duration_seconds=time.time() - t0,
                project_dir=str(project_dir)
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.websocket("/ws/build")
    async def ws_build(websocket: WebSocket):
        await websocket.accept()
        try:
            data = await websocket.receive_json()
            user_request = data.get("request", "")
            do_refine = data.get("refine", True)

            await websocket.send_json({"type": "status", "message": "Planning..."})
            plan = pipeline.plan(user_request)

            await websocket.send_json({
                "type": "plan",
                "plan": plan.to_dict()
            })

            project_dir = Config.PROJECTS_ROOT / plan.app_name
            await websocket.send_json({"type": "status", "message": "Generating files..."})
            files = await codegen.generate_project(plan, websocket=websocket, project_dir=project_dir)

            if do_refine:
                await websocket.send_json({"type": "status", "message": "Refining..."})
                files, fixes = refiner.refine(files, plan, websocket=websocket, project_dir=project_dir)
                await websocket.send_json({"type": "refinement_complete", "fixes": fixes})

            issues = CodeValidator.validate_project(files)
            await websocket.send_json({
                "type": "build_complete",
                "project_id": plan.id,
                "app_name": plan.app_name,
                "file_count": len(files),
                "files": list(files.keys()),
                "validation_issues": issues,
                "project_dir": str(project_dir)
            })

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass

    @app.get("/projects")
    async def list_projects():
        projects = []
        for p in Config.PROJECTS_ROOT.iterdir():
            if p.is_dir():
                file_count = sum(1 for _ in p.rglob("*") if _.is_file())
                projects.append({"name": p.name, "files": file_count, "path": str(p)})
        return {"projects": projects}

    @app.get("/projects/{name}")
    async def get_project(name: str):
        pdir = Config.PROJECTS_ROOT / name
        if not pdir.exists():
            raise HTTPException(status_code=404, detail="Project not found")
        files = []
        for f in pdir.rglob("*"):
            if f.is_file():
                rel = str(f.relative_to(pdir))
                size = f.stat().st_size
                files.append({"path": rel, "size": size})
        return {"name": name, "dir": str(pdir), "files": files}

    @app.get("/preview/{name}")
    async def preview_project(name: str):
        """Serve the project's index.html for preview."""
        pdir = Config.PROJECTS_ROOT / name
        html_file = pdir / "index.html"
        if html_file.exists():
            return HTMLResponse(html_file.read_text())
        raise HTTPException(status_code=404, detail="Preview not available")

    @app.post("/rag/rebuild")
    async def rebuild_rag():
        """Rebuild the RAG index from Base44 entities and existing projects."""
        rag.rebuild_index()
        return {"status": "ok", "documents": len(rag.documents)}

    @app.get("/components")
    async def list_components():
        return {"components": component_lib.list_components()}

    @app.get("/models")
    async def list_models():
        return {"models": ollama.list_models() if ollama.is_available() else []}

    return app


# ============================================================================
# CLI Interface
# ============================================================================

def cmd_start(args):
    """Start the builder server."""
    app = create_app()
    print(f"\n{'='*60}")
    print(f"  Frontier Elite Builder v2.0")
    print(f"  Port: {args.port}")
    print(f"  Ollama: {Config.OLLAMA_HOST}")
    print(f"  Projects: {Config.PROJECTS_ROOT}")
    print(f"  Components: {len(COMPONENT_TEMPLATES)} pre-built")
    print(f"{'='*60}\n")

    # Pre-warm: rebuild RAG index on startup
    ollama = OllamaClient()
    if ollama.is_available():
        print("Pre-warming: building RAG index...")
        rag = RAGEngine(ollama)
        rag.rebuild_index()
        print(f"RAG index: {len(rag.documents)} documents")

    uvicorn.run(app, host="0.0.0.0", port=args.port)


def cmd_check(args):
    """Health check."""
    ollama = OllamaClient()
    print(f"Ollama available: {ollama.is_available()}")
    if ollama.is_available():
        models = ollama.list_models()
        print(f"Models: {models}")
    router = ModelRouter(ollama)
    router.refresh_models()
    for t in TaskComplexity:
        model = router.route(t)
        print(f"  {t.value:10s} -> {model}")
    print(f"Components: {list(COMPONENT_TEMPLATES.keys())}")
    print(f"Projects root: {Config.PROJECTS_ROOT}")


def cmd_build(args):
    """Build a project from CLI."""
    ollama = OllamaClient()
    if not ollama.is_available():
        print("ERROR: Ollama is not available"); sys.exit(1)

    router = ModelRouter(ollama)
    router.refresh_models()
    rag = RAGEngine(ollama)
    component_lib = ComponentLibrary()
    pipeline = PlanningPipeline(ollama, router, rag, component_lib)
    codegen = CodeGenerator(ollama, router, component_lib)
    refiner = RefinementEngine(ollama, router)

    plan = pipeline.plan(args.request)
    if args.name:
        plan.app_name = args.name

    project_dir = Config.PROJECTS_ROOT / plan.app_name
    files = asyncio.run(codegen.generate_project(plan, websocket=None, project_dir=project_dir))

    if not args.no_refine:
        files, fixes = refiner.refine(files, plan, websocket=None, project_dir=project_dir)
        print(f"\nRefinement: {len(fixes)} fixes applied")

    issues = CodeValidator.validate_project(files)
    print(f"\nValidation issues: {len(issues)} files with issues")
    print(f"Project generated at: {project_dir}")
    print(f"Files: {len(files)}")


def cmd_install_components(args):
    """Install component library to a project directory."""
    lib = ComponentLibrary()
    target = Path(args.target)
    lib.install_to_project(target)
    print(f"Installed {len(COMPONENT_TEMPLATES)} components to {target}/src/components/ui/")


def main():
    parser = argparse.ArgumentParser(description="Frontier Elite Builder v2.0")
    subparsers = parser.add_subparsers(dest="command")

    # start
    p_start = subparsers.add_parser("start", help="Start the builder server")
    p_start.add_argument("--port", type=int, default=Config.BUILDER_PORT)
    p_start.add_argument("--ollama-host", default=Config.OLLAMA_HOST)

    # check
    p_check = subparsers.add_parser("check", help="Health check")

    # build
    p_build = subparsers.add_parser("build", help="Build a project from CLI")
    p_build.add_argument("request", help="App description/request")
    p_build.add_argument("--name", default="", help="Project name override")
    p_build.add_argument("--no-refine", action="store_true", help="Skip refinement")

    # install-components
    p_install = subparsers.add_parser("install-components", help="Install component library to a project")
    p_install.add_argument("target", help="Target project directory")

    args = parser.parse_args()

    if args.ollama_host:
        Config.OLLAMA_HOST = args.ollama_host

    if args.command == "start":
        cmd_start(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "install-components":
        cmd_install_components(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
