import json
from openai import OpenAI
from prompts import TRIPLE_EXTRACTION_PROMPT
from schemas import TRIPLE_EXTRACTION_SCHEMA

def extract_triples_from_string(input_text, output_file=None):
    """
    Extract semantic triples from a text string using QwQ-32B via LM Studio
    
    Args:
        input_text (str): Text string to analyze
        output_file (str, optional): Path to save the output JSON. If None, returns the result.
    
    Returns:
        dict: Extracted triples in JSON format
    """
    # Set up the QwQ-32B model via LM Studio
    client = OpenAI(
        base_url="http://192.168.2.94:1234/v1",  # LM Studio server URL
        api_key="not-needed",  # Not required for LM Studio
    )
    
    # Format prompt with input text
    prompt = TRIPLE_EXTRACTION_PROMPT.format(text=input_text)
    
    # Call the model with the prompt
    response = client.chat.completions.create(
        model="QwQ-32B",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "schema": TRIPLE_EXTRACTION_SCHEMA
            }
        }
    )

    # Parse the JSON response
    result = json.loads(response.choices[0].message.content)
    
    # Save the result if an output file is specified
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f"Results saved to {output_file}")
    
    return result

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