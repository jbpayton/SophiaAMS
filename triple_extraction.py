import os
import json
import time
from typing import Dict, List, Optional, Union
from openai import OpenAI
from dotenv import load_dotenv
from prompts import TRIPLE_EXTRACTION_PROMPT, CONVERSATION_TRIPLE_EXTRACTION_PROMPT
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
        except Exception:
            # If parsing fails, just use the original text
            text_to_extract = text
    
    # Choose the appropriate prompt based on content type
    if is_conversation:
        prompt = CONVERSATION_TRIPLE_EXTRACTION_PROMPT.format(text=text_to_extract)
    else:
        prompt = TRIPLE_EXTRACTION_PROMPT.format(text=text_to_extract)
    
    # Call the LLM
    response = client.chat.completions.create(
        model=os.getenv('EXTRACTION_MODEL', 'gemma-3-4b-it-qat'),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "schema": TRIPLE_EXTRACTION_SCHEMA
            }
        }
    )
    
    # Parse the response
    try:
        result = json.loads(response.choices[0].message.content)
        timestamp = timestamp or time.time()
        
        # Add speaker to each triple
        for triple in result.get("triples", []):
            triple["speaker"] = extracted_speaker
            
            # For summary triples, try to infer speaker from the subject if not already set
            if source and "_summary" in source and not extracted_speaker:
                subject_text = triple.get("subject", {}).get("text", "").lower()
                # Common entity names
                if subject_text in ["sophia", "assistant"]:
                    triple["speaker"] = "Sophia"
                elif subject_text in ["alex", "user"]:
                    triple["speaker"] = "Alex"
        
        # For queries, we want to return the extracted triples directly
        if is_query:
            return {
                "query_triples": result["triples"],
                "timestamp": timestamp,
                "text": text_to_extract,
                "speaker": extracted_speaker
            }
        
        # For regular extraction, return with metadata
        return {
            "triples": result["triples"],
            "source": source,
            "timestamp": timestamp,
            "text": text_to_extract,
            "speaker": extracted_speaker
        }
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