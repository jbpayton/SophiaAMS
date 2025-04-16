TRIPLE_EXTRACTION_PROMPT = """Extract structured triples from text for a knowledge graph. Each triple must have:
- Subject: The main entity being described
- Verb: A simple, clear relationship predicate (use basic verbs like "is", "has", "was", "created", "developed", etc.)
- Object: What the subject relates to

Critical rules:
1. Verb usage:
   - Use simple, clear verbs instead of complex phrases
   - For example, use "is" instead of "was the first member of"
   - Use "has" for possession and attributes
   - Use "was" for past states and events
   - Use "created" or "developed" for creation events
   - NEVER use "was" with ordinal information (e.g., "was the seventh" should be "is" with "position": "seventh" in object properties)
   - Place only adverbial modifiers in verb properties (describing how/when/where the action happens):
     * Manner: "quickly", "carefully", "eagerly"
     * Time: "yesterday", "in 2020", "during summer"
     * Location: "in the park", "at home", "on the table"
     * Frequency: "daily", "weekly", "occasionally"
     * Degree: "completely", "partially", "mostly"

2. Entity attributes:
   - Place descriptive adjectives in the properties of the subject or object:
     * Physical properties: "color": "blue", "size": "large", "shape": "round"
     * Material: "material": "wood", "metal", "plastic"
     * Age: "age": "new", "old", "ancient"
     * Condition: "condition": "broken", "worn", "pristine"
     * Purpose: "purpose": "decorative", "functional", "ceremonial"
     * Position/Order: "position": "second", "order": "first"
     * Source/Origin: "provided_by": "artist", "created_by": "company"
     * Type/Classification: "type": "vehicle", "category": "transportation"
     * Version/Model: "version": "2.0", "model": "2020"
     * Role/Form: "role": "android", "form": "humanoid", "appearance": "gothic"
   - Keep noun phrases intact but extract descriptive modifiers as properties
   - Include entity types in properties (e.g., "type": "vehicle", "category": "transportation")

3. Temporal and contextual information:
   - Include time periods in verb properties (e.g., "time": "2020", "period": "summer")
   - Include ordinal information in object properties (e.g., "order": "first", "position": "second")
   - Include source information in object properties when relevant
   - Include duration in properties (e.g., "duration": "2 hours", "lifespan": "5 years")

4. For ALL triples:
   - NEVER leave the object empty - if no clear object exists, use "unknown" or "unspecified"
   - Place all modifiers in appropriate properties
   - Use consistent formatting throughout
   - Ensure each triple is atomic and complete
   - Combine related information into single triples when possible
   - Extract all possible properties from the text

Example of correct role handling:
Input: "asked to draw person as a teacher"
Output:
{{
  "subject": {{
    "text": "artist",
    "properties": {{}}
  }},
  "verb": {{
    "text": "asked_to_draw",
    "properties": {{}}
  }},
  "object": {{
    "text": "person",
    "properties": {{
      "role": "teacher"
    }}
  }}
}}

Output as JSON following this exact structure:
{{
  "triples": [
    {{
      "subject": {{
        "text": "entity",
        "properties": {{}}
      }},
      "verb": {{
        "text": "relation",
        "properties": {{}}
      }},
      "object": {{
        "text": "target",
        "properties": {{}}
      }},
      "source_text": "exact_text_from_document"
    }}
  ]
}}

Text to analyze:
{text}"""