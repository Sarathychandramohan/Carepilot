"""
D:\\CarePilotAI\\backend\\app\\core\\settings.py
Central settings loaded from .env — covers Pillar A (Data & Retrieval) and
Pillar B (RAG Generation Pipeline) configuration.

SECURITY NOTE: All secrets (db_password, gemini_api_key) are read exclusively
from the .env file. They are NEVER hardcoded here. The .env file is git-ignored.
"""
from pydantic_settings import BaseSettings
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[3] / "backend" / ".env"


class Settings(BaseSettings):
    # ── Database ─────────────────────────────────────────────────────────────
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "carepilot_db"
    db_user: str = "postgres"
    db_password: str = ""       # Must be set in backend/.env — never hardcode

    # ── Synthea ───────────────────────────────────────────────────────────────
    synthea_seed: int = 42
    synthea_patient_count: int = 2000
    synthea_state: str = "Massachusetts"

    # ── Knowledge Base (Pillar A) ─────────────────────────────────────────────
    kb_snapshot_id: str = "v5"
    chroma_collection: str = "carepilot_kb_v5"
    bm25_index_path: str = "D:/CarePilotAI/rag_knowledge/bm25_index_v5.pkl"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # ── LLM — Local (Pillar B) ────────────────────────────────────────────────
    llm_local_model_path: str = "D:/CarePilotAI/models/qwen-4b-q4.gguf"
    llm_local_n_gpu_layers: int = 20        # Layers offloaded to RTX 2050
    llm_local_max_tokens: int = 1024

    # ── LLM — Gemini API Fallback (Pillar B) ─────────────────────────────────
    gemini_api_key: str = ""               # Set in backend/.env — never hardcode
    gemini_model: str = "gemini-1.5-flash"

    # ── Retrieval Configuration (Pillar B P5) ────────────────────────────────
    kb_dense_top_k: int = 15              # ChromaDB candidate pool size
    kb_bm25_top_k: int = 15              # BM25 candidate pool size
    kb_rrf_k: int = 60                    # Reciprocal Rank Fusion constant
    kb_final_top_n: int = 8              # Final KB chunks sent to LLM
    ehr_retrieval_k: int = 5             # EHR rows per category (lab, condition, rx)

    # ── Validation Thresholds (Pillar B P7) ──────────────────────────────────
    faithfulness_threshold: float = 0.80  # Citation coverage floor
    nli_entailment_threshold: float = 0.40  # NLI entailment floor per sentence

    # ── API Server ────────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:8081"

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def db_url_sync(self) -> str:
        return self.db_url

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
