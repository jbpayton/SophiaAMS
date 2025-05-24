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
   - NEVER combine ordinal information with verbs (e.g., "was the seventh" should be "is" with modifier in object)
   - Place ONLY adverbial modifiers in verb modifiers (describing how/when/where the action happens):
     * Manner: "manner": "quickly", "carefully", "eagerly"
     * Time: "time": "yesterday", "in 2020", "during summer"
     * Location: "location": "in the park", "at home", "on the table"
     * Frequency: "frequency": "daily", "weekly", "occasionally"
     * Degree: "degree": "completely", "partially", "mostly"

2. Entity attributes:
   - ALWAYS place adjectival phrases and descriptive terms in modifiers:
     * Physical qualities: "color": "blue", "size": "large", "shape": "round"
     * Material: "material": "wood", "metal", "plastic"
     * Age: "age": "new", "old", "ancient"
     * Condition: "condition": "broken", "worn", "pristine"
     * Purpose: "purpose": "decorative", "functional", "ceremonial"
     * Ordinal position: "position": "first", "second", "seventh"
     * Source/Origin: "source": "artist", "creator": "company"
     * Type/Classification: "type": "vehicle", "category": "transportation"
     * Version/Model: "version": "2.0", "model": "2020"
     * Role/Form: "role": "android", "form": "humanoid", "appearance": "gothic"
   - Keep the main noun intact in the text field but extract ALL descriptive modifiers as modifiers
   - Use modifier names that are linguistically appropriate for each modifier type

3. Temporal and contextual information:
   - Include time periods as modifiers (e.g., "time": "2020", "period": "summer")
   - Include ordinal information as modifiers (e.g., "order": "first", "position": "seventh")
   - For statements like "was the first X", use verb "is" with a modifier {{"position": "first"}}
   - Include source information when relevant as a modifier

4. For ALL triples:
   - NEVER leave the object empty - if no clear object exists, use "unknown" or "unspecified"
   - EXTRACT ALL DESCRIPTIVE ELEMENTS as modifiers, never leave them in the main text fields
   - The text fields should contain only the core nouns/verbs without modifiers
   - Split complex statements into multiple atomic triples when needed

Example of correct modifier usage:
Input: "The red sports car was quickly developed by Tesla in 2023"
Output:
{{
  "subject": {{
    "text": "car",
    "modifiers": {{
      "color": "red",
      "type": "sports"
    }}
  }},
  "verb": {{
    "text": "was_developed",
    "modifiers": {{
      "manner": "quickly",
      "time": "2023"
    }}
  }},
  "object": {{
    "text": "Tesla",
    "modifiers": {{
      "role": "company"
    }}
  }}
}}

Output as JSON following this exact structure:
{{
  "triples": [
    {{
      "subject": {{
        "text": "entity",
        "modifiers": {{}}
      }},
      "verb": {{
        "text": "relation",
        "modifiers": {{}}
      }},
      "object": {{
        "text": "target",
        "modifiers": {{}}
      }},
      "source_text": "exact_text_from_document"
    }}
  ]
}}

Text to analyze:
{text}"""

CONVERSATION_TRIPLE_EXTRACTION_PROMPT = """Extract structured triples from personal conversations for a knowledge graph. Each triple must have:
- Subject: The main entity being described (with proper speaker attribution)
- Verb: A simple, clear relationship predicate 
- Object: What the subject relates to (preserving ALL specific details)

The input format is: SPEAKER:name|dialogue_content

CRITICAL RULES:

1. **SPEAKER ATTRIBUTION** - Get this RIGHT:
   - The speaker name is EXPLICITLY given after "SPEAKER:" 
   - If the speaker says "I/my/me" → subject = the EXACT speaker name given
   - If the speaker says "you/your" → subject = the OTHER person's name (not the speaker)
   - If speaker talks about someone else → subject = that other person's name
   - NEVER use the speaker's name as subject when they say "you/your"

2. **PRESERVE ALL SPECIFIC DETAILS** - DO NOT GENERALIZE:
   - Keep exact dates, names, places, foods, items VERBATIM in objects
   - NEVER replace specific details with generic terms
   - Extract ALL descriptive elements as modifiers, never leave them in main text fields
   - The text fields should contain only core nouns/verbs without modifiers

3. **USE RICH MODIFIER STRUCTURE** like the regular extraction:
   - Physical qualities: "color", "size", "material", "condition"
   - Temporal: "time", "duration", "frequency", "period"
   - Descriptive: "type", "category", "role", "quality"
   - Contextual: "location", "manner", "degree"
   - EXTRACT ALL DESCRIPTIVE ELEMENTS as modifiers

4. **MEANINGFUL PREDICATES**:
   - Use simple, clear verbs: "has", "is", "enjoys", "prefers", "studies"
   - "has_birthday_on", "enjoys_activity", "listens_to_artist"
   - "prefers_food", "reads_author", "works_at", "studies_subject"

5. **For ALL triples**:
   - NEVER leave objects empty - preserve specific details
   - EXTRACT ALL DESCRIPTIVE ELEMENTS as modifiers
   - Split complex statements into multiple atomic triples when needed

EXAMPLES (completely generic to avoid contamination):

Input: SPEAKER:John|My car is a blue Honda and I drive it daily to work.
Output:
{{
  "subject": {{
    "text": "John",
    "modifiers": {{}}
  }},
  "verb": {{
    "text": "owns",
    "modifiers": {{}}
  }},
  "object": {{
    "text": "Honda",
    "modifiers": {{
      "color": "blue",
      "type": "car"
    }}
  }},
  "source_text": "My car is a blue Honda"
}},
{{
  "subject": {{
    "text": "John",
    "modifiers": {{}}
  }},
  "verb": {{
    "text": "drives_to",
    "modifiers": {{
      "frequency": "daily"
    }}
  }},
  "object": {{
    "text": "work",
    "modifiers": {{}}
  }},
  "source_text": "I drive it daily to work"
}}

Input: SPEAKER:Mary|Your presentation last Friday was really impressive! I live in Chicago.
Output:
{{
  "subject": {{
    "text": "listener",
    "modifiers": {{}}
  }},
  "verb": {{
    "text": "gave_presentation",
    "modifiers": {{
      "time": "last Friday"
    }}
  }},
  "object": {{
    "text": "presentation",
    "modifiers": {{
      "quality": "impressive"
    }}
  }},
  "source_text": "Your presentation last Friday was really impressive"
}},
{{
  "subject": {{
    "text": "Mary",
    "modifiers": {{}}
  }},
  "verb": {{
    "text": "lives_in",
    "modifiers": {{}}
  }},
  "object": {{
    "text": "Chicago",
    "modifiers": {{}}
  }},
  "source_text": "I live in Chicago"
}}

Output as JSON following this exact structure:
{{
  "triples": [
    {{
      "subject": {{
        "text": "entity",
        "modifiers": {{}}
      }},
      "verb": {{
        "text": "relation",
        "modifiers": {{}}
      }},
      "object": {{
        "text": "target_with_specific_details_preserved",
        "modifiers": {{}}
      }},
      "source_text": "exact_text_from_conversation"
    }}
  ]
}}

Text to analyze:
{text}"""

QUERY_EXTRACTION_PROMPT = """Please extract semantic triples from the following natural language query. The goal is to understand what information the user is looking for.

Guidelines:
1. Convert first-person statements (I, me, my) to use "user" as the subject
2. Convert questions into statement form
3. Extract the core relationship being expressed
4. Keep the original query text in the source_text field (no longer than a sentence or two)
5. Keep the context of the original text into account when extracting the triples.

Output format:
{{
    "triples": [
        {{
            "subject": {{"text": "subject_text", "modifiers": {{}}}},
            "verb": {{"text": "verb_text", "modifiers": {{}}}},
            "object": {{"text": "object_text", "modifiers": {{}}}},
            "source_text": "original_query_text"
        }}
    ]
}}

Query to analyze:
{text}"""