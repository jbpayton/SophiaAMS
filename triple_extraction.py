import os
import json
import time
from typing import Dict, List, Optional, Union
from openai import OpenAI
from dotenv import load_dotenv
from prompts import TRIPLE_EXTRACTION_PROMPT
from schemas import TRIPLE_EXTRACTION_SCHEMA

# Load environment variables
load_dotenv()

def extract_triples_from_string(
    text: str, 
    source: Optional[str] = None,
    timestamp: Optional[float] = None,
    is_query: bool = False
) -> Dict:
    """
    Extract semantic triples from a text string.
    
    Args:
        text: Input text to extract triples from
        source: Optional source identifier for the text
        timestamp: Optional timestamp for when the information was received
        is_query: Whether this is a query (affects how we process the results)
        
    Returns:
        Dict containing extracted triples and metadata
    """
    client = OpenAI(
        base_url=os.getenv('LLM_API_BASE'),
        api_key=os.getenv('LLM_API_KEY'),
    )
    
    # Prepare the prompt with the input text
    prompt = TRIPLE_EXTRACTION_PROMPT.format(text=text)
    
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
        
        # For queries, we want to return the extracted triples directly
        if is_query:
            return {
                "query_triples": result["triples"],
                "timestamp": timestamp,
                "text": text
            }
        
        # For regular extraction, return with metadata
        return {
            "triples": result["triples"],
            "source": source,
            "timestamp": timestamp,
            "text": text
        }
    except Exception as e:
        print(f"Error parsing response: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
        return {
            "triples": [],
            "source": source,
            "timestamp": timestamp or time.time(),
            "text": text,
            "error": str(e)
        }

if __name__ == "__main__":
    # Example usage
    sample_text = """
    Hatsune Miku (初音ミク), codenamed CV01, was the first Japanese VOCALOID to be both developed and distributed by Crypton Future 
    Media, Inc.. She was initially released in August 2007 for the VOCALOID2 engine and was the first member of the Character Vocal 
    Series. She was the seventh VOCALOID overall, as well as the second VOCALOID2 vocal released to be released for the engine. Her 
    voice is provided by the Japanese voice actress Saki Fujita (藤田咲, Fujita Saki)

    When KEI illustrated Miku, he was given a color scheme to work with (based on the YAMAHA synthesizers' signature blue-green colour) 
    and was asked to draw Miku as an android. Crypton also provided KEI with Miku's detailed concepts, however, Crypton said it was not 
    easy to explain what a "Vocaloid" was to him. KEI said he could not create an image of a "singing computer" at first, as he did not 
    even know what a "synthesizer" was. It took him more than a month to complete the commission.
    """
    
    # Extract triples
    extracted_triples = extract_triples_from_string(sample_text)
    
    # Pretty print the result
    print(json.dumps(extracted_triples, indent=2)) 