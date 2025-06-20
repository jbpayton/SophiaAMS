TRIPLE_EXTRACTION_PROMPT = """Extract structured triples from text for a knowledge graph. Each triple must have:
- Subject: The main entity being described
- Verb: A complete relationship predicate that captures the full action/relationship
- Object: The specific entity or value that the subject relates to
- Topics: A list of primary themes or categories relevant to this specific fact, considering the overall context of the entire input text. These should reflect broader concepts present in the full text.

Rules:
1. For EACH triple, identify a list of concise and relevant topics for that specific piece of information, considering the overall themes of the entire input text.
2. Use complete, meaningful verbs that capture the full relationship (e.g., "was developed by", "voice is provided by", "was released for").
3. Objects should be specific entities, not partial actions (e.g., "Crypton Future Media" not "developed").
4. Never leave the object empty - if no clear object exists, use "unknown" or "unspecified" for the object.
5. Preserve important details like dates, locations, and specific entities in objects.
6. The 'topics' field (note the plural) should be a list of strings. Each string in the list represents a relevant topic for that individual triple, derived from the overall themes of the entire input text.

Examples:
- Input Text: "Hatsune Miku was developed by Crypton Future Media. She was released in August 2007. Her voice is provided by Saki Fujita. She is a virtual singer. This technology is part of Japan's digital entertainment industry."
  Output would include:
  {{ "subject": "Hatsune Miku", "verb": "was developed by", "object": "Crypton Future Media", "source_text": "Hatsune Miku was developed by Crypton Future Media", "topics": ["Virtual Singer Development", "Character Vocal Series", "Japanese Digital Entertainment"] }}
  {{ "subject": "Hatsune Miku", "verb": "was released in", "object": "August 2007", "source_text": "She was released in August 2007", "topics": ["VOCALOID Release History", "Virtual Singer Development", "Japanese Digital Entertainment"] }}
  {{ "subject": "Hatsune Miku", "verb": "voice is provided by", "object": "Saki Fujita", "source_text": "Her voice is provided by Saki Fujita", "topics": ["Voice Actress Information", "Virtual Singer Development", "Japanese Digital Entertainment"] }}
  {{ "subject": "Hatsune Miku", "verb": "is a", "object": "virtual singer", "source_text": "She is a virtual singer", "topics": ["Occupation/Type", "Virtual Singer Development", "Japanese Digital Entertainment"] }}

Output as JSON following this exact structure:
{{
  "triples": [
    {{
      "subject": "entity",
      "verb": "complete_relationship",
      "object": "specific_target",
      "source_text": "exact_text_from_document",
      "topics": ["relevant_topic_1_from_global_context", "relevant_topic_2_from_global_context"]
    }}
    // ... more triples, each with its own list of topics
  ]
}}

Text to analyze:
{text}"""

CONVERSATION_TRIPLE_EXTRACTION_PROMPT = """Extract personal facts from conversation into knowledge triples.

Input format: SPEAKER:name|dialogue

CORE RULES:

1. **Speaker Attribution (CRITICAL)**:
   - "I/my/me" in dialogue → subject = speaker's name (the name after SPEAKER:)
   - "you/your" in dialogue → subject = the other person's name (not the current speaker)
   - Always use actual person names from the SPEAKER: tags, never "user" or "assistant".
   - Pay careful attention to who is speaking when attributing facts.

2. **Extract Clear Facts**:
   - Focus on factual information being shared about people.
   - For EACH fact, identify a list of concise topics (e.g., ["Likes/Dislikes", "Personal Interests"], ["Work Details", "Career Information"], ["Hobbies", "Leisure Activities"], ["Personal Details", "Biography"]). These topics should consider the overall context of the conversation.
   - Use complete, meaningful verbs that capture the full relationship.
   - Objects should be specific entities, not partial actions.
   - Keep specific details like names, places (be as complete as possible when specifying a place), dates, foods, etc.
   - Ignore conversational filler or emotional responses.

3. **Complete Relationships & Topics**:
   - Subject: person's name
   - Verb: complete relationship (likes, works_at, lives_in, was_born_on, etc.)
   - Object: specific target entity
   - Topics: A list of brief categories for this specific fact, considering the overall context of the entire conversation.

Example:
Input: "SPEAKER:Sophia|I love sushi and work at Google. I'm interested in AI and machine learning, especially for creative applications."
Output:
{{
  "triples": [
    {{
      "subject": "Sophia",
      "verb": "loves",
      "object": "sushi",
      "source_text": "I love sushi",
      "topics": ["Food Preference", "Personal Interests"]
    }},
    {{
      "subject": "Sophia", 
      "verb": "works_at",
      "object": "Google",
      "source_text": "work at Google",
      "topics": ["Employment", "Career Information"]
    }},
    {{
      "subject": "Sophia",
      "verb": "is interested in",
      "object": "AI",
      "source_text": "I\'m interested in AI",
      "topics": ["Interest", "Technology", "Creative Applications"]
    }},
    {{
      "subject": "Sophia",
      "verb": "is interested in",
      "object": "machine learning",
      "source_text": "I\'m interested in machine learning",
      "topics": ["Interest", "Technology", "Creative Applications"]
    }}
  ]
}}

Text to analyze:
{text}"""

QUERY_EXTRACTION_PROMPT = """Please extract semantic triples from the following natural language query. The goal is to understand what information the user is looking for. Each triple must include a 'topics' field.

Guidelines:
1. Convert first-person statements (I, me, my) to use "user" as the subject.
2. Convert questions into statement form.
3. Use complete, meaningful verbs that capture the full relationship being queried.
4. Objects should be specific entities or values, not partial actions.
5. Keep the original query text in the source_text field.
6. For EACH triple, identify a list of concise and relevant topics for that specific piece of information, considering the overall themes of the entire query.
7. The 'topics' field should be a list of strings.

Output format:
{{
    "triples": [
        {{
            "subject": "subject_text",
            "verb": "complete_relationship",
            "object": "specific_target",
            "source_text": "original_query_text",
            "topics": ["relevant_topic_1_from_query_context", "relevant_topic_2_from_query_context"]
        }}
    ]
}}

Query to analyze:
{text}"""

CONTENT_ANALYSIS_PROMPT = """
Analyze this HTML content and identify the main content area. Look for:
1. The primary article/content area
2. Navigation/sidebar elements to exclude
3. Footer/header elements to exclude

Return a JSON object with:
{{
    "main_content_selectors": ["list", "of", "selectors"],
    "exclude_selectors": ["list", "of", "selectors"],
    "content_type": "wiki/article/blog/etc",
    "confidence": "high/medium/low"
}}

HTML content:
{content}
"""

CHUNK_FILTERING_PROMPT = """Review each text chunk. Your primary goal is to distinguish between:
1. Informational/Explanatory Content: Text that explains, describes, or narrates a topic. This includes:
    - Narrative paragraphs.
    - Explanations that incorporate citations (e.g., [1], (Smith 2020)).
    - Lists of features, characteristics, steps, components, examples, product/work titles (e.g., software versions, album names by the discussed artist), or other details that are *integral to and part of the main explanation* of the topic. These lists provide direct information *about the subject itself*, even if individual items within such lists are cited.
    - Tables or infoboxes that present information directly related to the topic.
    This content should be KEPT.

2. External Reference & Pure Navigation Lists: Text that primarily serves to point to external resources, or is purely for navigating the document or related topics, rather than explaining the topic itself. This content should be DISCARDED. This includes:
    a) Bibliographies, reference lists, or citation lists: Characterized by multiple itemized entries that primarily point to *external sources* (e.g., lists of articles, books, research papers, with details like authors, dates, titles, DOIs, external URLs).
    b) Purely navigational sections: Such as lists of keywords for searching, "See Also" sections *that are predominantly collections of links or pointers to other topics/articles*, "External Links" sections, or sidebars that are just lists of links.
    c) Tables of contents or indices: That are structured lists primarily for document navigation.

GUIDELINES FOR DECISION:

1.  **CRITICAL LIST EVALUATION (For any chunk that appears list-like, start here):**
    *   First, identify what the **list items themselves** represent (momentarily ignore citations attached *to* these items or minor interspersed external links).
    *   **KEEP THE CHUNK IF** the majority of these list items are: **factual details, characteristics, events, components, product names (e.g., different Vocaloid software versions, specific song titles from a Vocaloid artist's discography being discussed), technical specifications, or data points (e.g., chart positions for relevant works) *directly describing or belonging to the main document topic*.**
        *   The presence of citations for these factual list items, or a few interspersed external links, does NOT automatically make the chunk discardable IF the core list items provide valuable, topic-specific information.
    *   **DISCARD THE CHUNK IF** the list items *themselves* are predominantly: **bibliographic entries (Author, Title, Year, Publisher, external URL), or purely navigational links pointing to other articles/sections or external websites.**

2.  **OVERALL CHUNK PURPOSE (For all chunks, reinforcing the list evaluation):**
    *   Is the chunk's primary contribution to *explain or describe the topic at hand* (KEEP IT)? This includes narrative text and factual lists as defined above.
    *   Or, is it primarily a *gateway to external information or for pure navigation* (DISCARD IT)? This includes bibliographies and lists of external links.

3.  **CONTEXTUAL CUES:**
    *   Chunks from the end of the document (indicated by "This chunk is from the end of the document") are more likely to be discardable external reference lists. However, if such a chunk contains a list of topic-specific factual data (e.g., a complete list of official product versions) or is a narrative conclusion, it should be KEPT based on the rules above.

FORMAT YOUR ANSWER EXACTLY LIKE THIS (one line per chunk, provide a concise reason based on the distinctions above):
CHUNK N: KEEP - Brief reason (e.g., Explains a core concept; Lists factual data about the topic like product features/events/technical specs; Describes components/history)
CHUNK M: DISCARD - Brief reason (e.g., Primarily a list of external bibliographic sources; Navigational list of other topics/sites)
CHUNK P (This chunk is from the end of the document): DISCARD - Brief reason (e.g., Bibliography section at end of document; List of external links at end)

{batch_texts}"""