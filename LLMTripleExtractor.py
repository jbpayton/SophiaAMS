import json
import re
from typing import List, Tuple, Dict, Any
from TripleExtractor import TripleExtractor
from ContextSummarizers import summarize_messages_tuples_simpler

class LLMTripleExtractor(TripleExtractor):
    def __init__(self, client):
        """
        Initialize the LLM-based triple extractor.
        
        Args:
            client: The LLM client to use for extraction
        """
        self.client = client

    def clean_json(self, json_string: str) -> str:
        """
        Clean JSON string by removing unescaped control characters.
        
        Args:
            json_string: The JSON string to clean
            
        Returns:
            Cleaned JSON string
        """
        return re.sub(r'[\x00-\x1F]', '', json_string)

    def extract_triples(self, text: str) -> Tuple[List[Tuple[str, str, str]], List[Dict[str, Any]]]:
        """
        Extract triples using the LLM client.
        
        Args:
            text: The input text to extract triples from
            
        Returns:
            A tuple containing:
            - List of triples (subject, relationship, object)
            - List of metadata dictionaries for each triple
        """
        triples_list = []
        
        # Use the existing summarizer to get the triples
        tuples_output = summarize_messages_tuples_simpler(self.client, text)
        
        # Clean and parse the JSON output
        data = json.loads(self.clean_json(tuples_output))
        
        # Convert the data into triples and metadata
        for triple in data:
            try:
                subject = triple['subject']
                relationship = triple['relationship']
                obj = triple['object']
                
                # Create the triple tuple
                triples_list.append((subject, relationship, obj))
            except KeyError:
                print("Error: Triple missing subject, relationship, or object")
                continue

        return triples_list, data 