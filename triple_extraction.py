import os
import json
import time
from typing import Dict, List, Optional, Union
from openai import OpenAI
from dotenv import load_dotenv
from prompts import (TRIPLE_EXTRACTION_PROMPT, CONVERSATION_TRIPLE_EXTRACTION_PROMPT,
                      QUERY_EXTRACTION_PROMPT, PROCEDURAL_KNOWLEDGE_EXTRACTION_PROMPT)
from schemas import TRIPLE_EXTRACTION_SCHEMA

# Load environment variables
load_dotenv()

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
    response = client.chat.completions.create(
        model=os.getenv('EXTRACTION_MODEL', 'gemma-3-4b-it-qat'),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=extraction_max_tokens
    )
    
    # Parse the response
    try:        
        content = response.choices[0].message.content
        if content:
            # Attempt to strip <think>...</think> block if present
            think_start_tag = "<think>"
            think_end_tag = "</think>"
            if content.strip().startswith(think_start_tag) and think_end_tag in content:
                think_end_index = content.rfind(think_end_tag)
                json_content_start = think_end_index + len(think_end_tag)
                actual_json_content = content[json_content_start:].strip()
                if actual_json_content:
                    # Found JSON after </think>
                    result = json.loads(actual_json_content)
                else:
                    # Nothing after </think>; attempt to parse JSON *inside* the think block
                    think_inner = content[len(think_start_tag):think_end_index].strip()
                    try:
                        result = json.loads(think_inner)
                    except Exception:
                        print("Warning: Could not parse JSON inside <think> block. Returning empty triples.")
                        result = {"triples": []}

            else: # No <think> block detected, try to parse directly
                # Strip markdown code blocks if present
                if content.strip().startswith('```json') and content.strip().endswith('```'):
                    json_start = content.find('```json') + 7
                    json_end = content.rfind('```')
                    actual_json_content = content[json_start:json_end].strip()
                    result = json.loads(actual_json_content)
                elif content.strip().startswith('```') and content.strip().endswith('```'):
                    # Handle generic code blocks
                    json_start = content.find('```') + 3
                    json_end = content.rfind('```')
                    actual_json_content = content[json_start:json_end].strip()
                    result = json.loads(actual_json_content)
                else:
                    result = json.loads(content)
        else:
            result = {"triples": []}
        
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
        print(f"Error parsing response: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
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