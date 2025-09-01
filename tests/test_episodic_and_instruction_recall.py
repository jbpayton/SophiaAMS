#!/usr/bin/env python3
"""
Episodic & Instruction Recall Benchmark (stand-alone)
====================================================
Run this file directly:
    python tests/test_episodic_and_instruction_recall.py

It will
1. spin up a fresh VectorKnowledgeGraph in a temp folder,
2. ingest one instruction episode (Alex asking to run `deploy.sh` and then
   POST to `/api/restart`),
3. issue two recall queries, and
4. ask the same LLM used elsewhere in the repo to grade whether the
   summaries returned by `AssociativeSemanticMemory.query_related_information`
   contain the expected keywords.

The script exits with code 0 on success and 1 on failure.  If the required
LLM credentials (`LLM_API_KEY`) are not present it **skips** the test and
exits 0 so CI won't break on credential-less environments.
"""
from __future__ import annotations

import os
import sys
import time
import shutil
import logging
from datetime import datetime
from typing import List
from dotenv import load_dotenv
from openai import OpenAI

# Project imports – add repo root to path first
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from VectorKnowledgeGraph import VectorKnowledgeGraph  # type: ignore
from AssociativeSemanticMemory import AssociativeSemanticMemory  # type: ignore
from utils import setup_logging  # type: ignore

load_dotenv()

TEST_DIR = "test-output/Test_EpisodicInstructionMemory"

# ---------------------------------------------------------------------------
# Helper: simple grader using the project LLM
# ---------------------------------------------------------------------------

def get_llm_client() -> OpenAI:
    return OpenAI(
        base_url=os.getenv("LLM_API_BASE"),
        api_key=os.getenv("LLM_API_KEY"),
    )


def llm_grade(question: str, expected_keywords: List[str], answer: str) -> tuple[bool, str]:
    """Return True if LLM judges *answer* acceptable and containing all keywords."""

    system_msg = (
        "You are an automated unit-test grader. Respond with PASS if and only if "
        "the provided ANSWER would satisfy a reasonable human for the QUESTION "
        "and includes *all* of the required keywords (case-insensitive). "
        "Otherwise respond with FAIL. Reply with exactly one word: PASS or FAIL."
    )

    user_msg = (
        f"QUESTION: {question}\n"
        f"REQUIRED KEYWORDS: {', '.join(expected_keywords)}\n"
        f"ANSWER: {answer}"
    )

    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=os.getenv("EXTRACTION_MODEL", "gemma-3-4b-it-qat"),
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=500,
        )

        raw = resp.choices[0].message.content.strip()

        # Some models wrap thoughts inside <think>...</think>. Remove that wrapper if present.
        if raw.startswith("<think>") and "</think>" in raw:
            raw = raw.split("</think>", 1)[1].strip()

        first_token = raw.split()[0].upper() if raw else ""
        passed = first_token.startswith("PASS")
        return passed, raw
    except Exception as exc:
        logging.error(f"LLM grader error: {exc}")
        return False, ""

# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------

def main() -> None:
    # Skip gracefully if no LLM creds
    if not os.getenv("LLM_API_KEY"):
        print("[SKIP] LLM_API_KEY env var not set – episodic recall benchmark skipped.")
        sys.exit(0)

    # Logging setup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"test-output/episodic_instruction_recall_{ts}.log"
    setup_logging(debug_mode=True, log_file=log_path)
    # Ensure console output shows DEBUG level so we can inspect graph operations live
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.DEBUG)
        handler.flush()

    # Build memory infrastructure
    kgraph = VectorKnowledgeGraph(path=TEST_DIR)
    memory = AssociativeSemanticMemory(kgraph)

    try:
        # ------------------------------------------------------------------
        # 1. Ingest instruction episodes (only once per run)
        # ------------------------------------------------------------------
        instruction_text = (
            "SPEAKER:Alex|Please connect to server 'alpha' via SSH on port 2222 "
            "and run the deploy.sh script. After that, call the /api/restart "
            "endpoint with a POST request containing JSON {\"service\":\"web\"}."
        )
        memory.ingest_text(
            text=instruction_text,
            source="instructions_episode",
            timestamp=time.time(),
            speaker="Alex",
        )

        # Second, more complex multi-step instruction episode
        instruction_text2 = (
            "SPEAKER:Jordan|To create a full website backup you must: "
            "1) stop the web service using `systemctl stop web`; "
            "2) archive the directory /var/www into a file named `backup_$(date +%F).tar.gz`; "
            "3) restart the service with `systemctl start web`."
        )
        memory.ingest_text(
            text=instruction_text2,
            source="backup_procedure_episode",
            timestamp=time.time(),
            speaker="Jordan",
        )

        # ------------------------------------------------------------------
        # Inspect the current contents of the knowledge graph
        # ------------------------------------------------------------------
        print("\n--- CURRENT TRIPLES IN GRAPH ---")
        for triple_data in kgraph.get_all_triples():
            print(triple_data)
        print("--- END OF TRIPLES ---\n")

        # ------------------------------------------------------------------
        # 2. Run queries and grade
        # ------------------------------------------------------------------
        tests = [
            # Episode 1 checks
            ("What script did Alex ask to run on server alpha?", ["deploy.sh", "alpha"]),
            ("Which endpoint should be called to restart the service?", ["/api/restart", "post"]),

            # Episode 2 checks (multi-step backup)
            ("Which command stops the web service before backup?", ["systemctl", "stop", "web"]),
            ("After the backup, how do we restart the service?", ["systemctl", "start", "web"]),
            ("What archive file is created during the backup process?", ["backup_", ".tar.gz"]),
        ]
        all_passed = True
        for question, keywords in tests:
            print("\nQUESTION:", question)

            thresholds = [0.6, 0.4, 0.2, 0.0]
            summary = ""
            used_threshold = None

            for thr in thresholds:
                result = memory.query_related_information(
                    text=question,
                    entity_name="MemoryAgent",
                    limit=5,
                    min_confidence=thr,
                    include_summary_triples=True,
                    hop_depth=1,
                    return_summary=True,
                    include_triples=False,
                )
                summary = result.get("summary", "")
                if summary and not summary.lower().startswith("no relevant information"):
                    used_threshold = thr
                    break  # found useful info

            if used_threshold is None:
                used_threshold = thresholds[-1]

            print(f"THRESHOLD USED: {used_threshold}")
            print("SUMMARY :", summary)

            ok, raw_response = llm_grade(question, keywords, summary)
            print("RESULT  :", "PASS" if ok else "FAIL")
            print("RAW RESPONSE:", raw_response)
            all_passed = all_passed and ok

        # ------------------------------------------------------------------
        # 3. Exit status
        # ------------------------------------------------------------------
        if all_passed:
            print("\n✅ Episodic instruction recall benchmark passed.")
            code = 0
        else:
            print("\n❌ Episodic instruction recall benchmark failed.")
            code = 1

    finally:
        # Clean up
        try:
            memory.close()
        except Exception:
            pass
        if os.path.exists(TEST_DIR):
            time.sleep(0.5)
            shutil.rmtree(TEST_DIR, ignore_errors=True)

    sys.exit(code)


if __name__ == "__main__":
    main() 