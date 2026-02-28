import os
import json
import re
import time
import logging
from typing import Dict, List, Optional, Union
from openai import OpenAI
from dotenv import load_dotenv
from prompts import (TRIPLE_EXTRACTION_PROMPT, CONVERSATION_TRIPLE_EXTRACTION_PROMPT,
                      QUERY_EXTRACTION_PROMPT, PROCEDURAL_KNOWLEDGE_EXTRACTION_PROMPT)
from schemas import TRIPLE_EXTRACTION_SCHEMA

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def _extract_json(content: str) -> dict:
    """
    Robustly extract JSON from LLM output that may contain chain-of-thought,
    <think> blocks, markdown fences, or other preamble before the actual JSON.

    Strategy (in order):
    1. Strip <think>...</think> blocks
    2. Extract from ```json fences
    3. Find the last top-level JSON object in the text
    4. Fall back to empty triples
    """
    # 1. Strip <think>...</think> blocks (greedy — remove all of them)
    cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

    # 2. Try markdown ```json ... ``` fences
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', cleaned, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Try direct parse (works when content is pure JSON)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 4. Find the last { ... } block (models often put reasoning before JSON)
    #    We search from the end to get the actual JSON, not a stray { in reasoning.
    brace_depth = 0
    json_end = -1
    json_start = -1
    for i in range(len(cleaned) - 1, -1, -1):
        ch = cleaned[i]
        if ch == '}':
            if brace_depth == 0:
                json_end = i
            brace_depth += 1
        elif ch == '{':
            brace_depth -= 1
            if brace_depth == 0 and json_end != -1:
                json_start = i
                break

    if json_start != -1 and json_end != -1:
        candidate = cleaned[json_start:json_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 5. Give up
    logger.warning("Could not extract JSON from LLM response (%d chars). Returning empty triples.", len(content))
    return {"triples": []}


def extract_triples_from_string(
    text: str, 
    source: Optional[str] = None,
    timestamp: Optional[float] = None,
    is_query: bool = False,
    speaker: Optional[str] = None,
    is_conversation: bool = False
) -> Dict:
    """
    Extract semantic triples from a text string.
    Topics are now an integral part of each triple.
    
    Args:
        text: Input text to extract triples from
        source: Optional source identifier for the text
        timestamp: Optional timestamp for when the information was received
        is_query: Whether this is a query (affects how we process the results)
        speaker: Optional identifier for who generated this text
        is_conversation: Whether this text is from a conversation (uses specialized prompt)
        
    Returns:
        Dict containing extracted triples and metadata
    """
    client = OpenAI(
        base_url=os.getenv('LLM_API_BASE'),
        api_key=os.getenv('LLM_API_KEY'),
    )
    
    # Parse any speaker information from the text itself
    # Format: SPEAKER:name|content
    text_to_extract = text
    extracted_speaker = speaker
    if not is_query and text.startswith("SPEAKER:"):
        try:
            speaker_parts = text.split("|", 1)
            if len(speaker_parts) == 2:
                extracted_speaker = speaker_parts[0].replace("SPEAKER:", "").strip()
                text_to_extract = speaker_parts[1].strip()
            # If speaker is not explicitly provided in the text, and it's not a query,
            # and a speaker argument was passed, use that.
            # Otherwise, it remains None or the parsed speaker.
        except Exception:
            # If parsing fails, just use the original text
            text_to_extract = text
    elif speaker: # If speaker is provided as an argument and not parsed from text
        extracted_speaker = speaker
    # If no speaker is identified from text or arguments, it defaults to None.
    # For general documents, speaker will often be None.
    
    # Choose the appropriate prompt based on content type
    if is_conversation:
        prompt = CONVERSATION_TRIPLE_EXTRACTION_PROMPT.format(text=text_to_extract)
    elif is_query:
        prompt = QUERY_EXTRACTION_PROMPT.format(text=text_to_extract)
    else:
        # Detect procedural knowledge patterns (how-to instructions, methods, etc.)
        text_lower = text_to_extract.lower()

        # Strong procedural indicators (high weight)
        strong_indicators = [
            'to send', 'to use', 'to install', 'to deploy', 'to build', 'to run',
            'you can use', 'you need to', 'you should use',
            'how to', 'steps to', 'method for',
            'example:', 'for example:', 'for instance:',
            'first,', 'then,', 'next,', 'finally,',
            'alternatively,', 'instead of',
        ]

        # Moderate indicators (medium weight)
        moderate_indicators = [
            'use requests', 'use pip', 'use npm', 'use docker',
            'install ', 'pip install', 'npm install',
            'import ', 'from ', 'def ', 'function ',
            ' requires ', ' requires_', 'required to',
            '.post(', '.get(', '.put(', '.delete(',
        ]

        # Count indicators with weights
        strong_score = sum(2 for indicator in strong_indicators if indicator in text_lower)
        moderate_score = sum(1 for indicator in moderate_indicators if indicator in text_lower)
        procedural_score = strong_score + moderate_score

        # Detect step-based instruction style (numbered steps or shell commands)
        looks_like_instruction = any(
            token in text_to_extract for token in ['`', '1)', '2)', '1.', '2.', 'systemctl', 'mkdir', 'backup_', 'deploy.sh']
        )

        # Use procedural prompt if enough indicators or clear instructional style
        # Threshold: 5 (e.g., 2 strong + 1 moderate, or 5 moderate)
        if procedural_score >= 5 or looks_like_instruction:
            prompt = PROCEDURAL_KNOWLEDGE_EXTRACTION_PROMPT.format(text=text_to_extract)
        else:
            prompt = TRIPLE_EXTRACTION_PROMPT.format(text=text_to_extract)
    
    # Respect an environment knob for output length; default generously high
    extraction_max_tokens = int(os.getenv('EXTRACTION_MAX_TOKENS', '2048'))
    context_window = int(os.getenv('LLM_CONTEXT_WINDOW', '0'))

    # Truncate prompt if it would exceed the context window
    if context_window > 0:
        max_input_chars = (context_window - extraction_max_tokens - 256) * 4
        if len(prompt) > max_input_chars > 0:
            import logging
            logging.getLogger(__name__).warning(
                f"Truncating extraction prompt from {len(prompt)} to {max_input_chars} chars "
                f"(context_window={context_window})"
            )
            prompt = prompt[:max_input_chars]

    response = client.chat.completions.create(
        model=os.getenv('EXTRACTION_MODEL', 'gemma-3-4b-it-qat'),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=extraction_max_tokens,
        extra_body={"enable_thinking": False},  # LM Studio: skip chain-of-thought
    )
    
    # Parse the response
    try:
        content = response.choices[0].message.content
        result = _extract_json(content) if content else {"triples": []}
        
        timestamp = timestamp or time.time()

        # Add speaker and procedural metadata to each triple if not already present from LLM
        for triple in result.get("triples", []):
            if "speaker" not in triple or triple["speaker"] is None:
                triple["speaker"] = extracted_speaker

            # Detect if this is a procedural triple and add metadata
            topics = triple.get("topics", [])
            verb = triple.get("verb", "").lower()

            # Check if using procedural predicates
            procedural_verbs = [
                "accomplished_by", "alternatively_by", "requires", "requires_prior",
                "enables", "is_method_for", "example_usage", "has_step", "followed_by"
            ]
            is_procedural = verb in procedural_verbs or "procedure" in topics

            if is_procedural:
                # Ensure "procedure" is in topics
                if "procedure" not in topics:
                    topics.append("procedure")
                    triple["topics"] = topics

                # Add abstraction_level if not present
                if "abstraction_level" not in triple:
                    # Infer abstraction level from context
                    if any(x in verb for x in ["example_usage", "import", "install"]):
                        triple["abstraction_level"] = 1  # Atomic
                    elif any(x in verb for x in ["accomplished_by", "requires", "enables"]):
                        triple["abstraction_level"] = 2  # Basic procedure
                    else:
                        triple["abstraction_level"] = 3  # High-level task
            
            # For summary triples, try to infer speaker from the subject if not already set
            if source and "_summary" in source and not extracted_speaker:
                subject_text = triple.get("subject", "").lower()
                # Common entity names
                if subject_text in ["sophia", "assistant"]:
                    triple["speaker"] = "Sophia"
                elif subject_text in ["alex", "user"]:
                    triple["speaker"] = "Alex"
        
        # Speaker information is now expected to be part of the triples 
        # returned by the LLM if the prompt requests it (e.g. for conversation_triple_extraction)
        # or added by the logic above for summary triples.
        # Topic triples are also expected to be directly in the result["triples"] list.

        # For queries, we want to return the extracted triples directly
        if is_query:
            query_result = {
                "query_triples": result.get("triples", []),
                "timestamp": timestamp,
                "text": text_to_extract,
                "speaker": extracted_speaker # This will be "user" for queries as per prompt
            }
            return query_result
        
        # For regular extraction, return with metadata
        extraction_result = {
            "triples": result.get("triples", []),
            "source": source,
            "timestamp": timestamp,
            "text": text_to_extract,
            "speaker": extracted_speaker
        }
        
        return extraction_result
    except Exception as e:
        logger.error("Error parsing extraction response: %s", e)
        logger.debug("Raw response: %s", response.choices[0].message.content[:500] if response.choices else "(empty)")
        return {
            "triples": [],
            "source": source,
            "timestamp": timestamp or time.time(),
            "text": text_to_extract,
            "speaker": extracted_speaker,
            "error": str(e)
        }

if __name__ == "__main__":
    # Example usage
    sample_text = """
    Hatsune Miku (初音ミク), codenamed CV01, was the first Japanese VOCALOID to be both developed and distributed by Crypton Future 
    Media, Inc.. She was initially released in August 2007 for the VOCALOID2 engine and was the first member of the Character Vocal 
    Series. She was the seventh VOCALOID overall, as well as the second VOCALOID2 vocal released to be released for the engine. Her 
    voice is provided by the Japanese voice actress Saki Fujita (藤田咲, Fujita Saki)
    """
    
    # Extract triples
    start_time = time.time()
    extracted_triples = extract_triples_from_string(sample_text)
    end_time = time.time()
    
    # Pretty print the result
    print(json.dumps(extracted_triples, indent=2)) 
    print(f"Time taken: {end_time - start_time} seconds")