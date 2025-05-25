TRIPLE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "verb": {"type": "string"},
                    "object": {"type": "string"},
                    "source_text": {"type": "string"},
                    "speaker": {"type": ["string", "null"]},
                    "topics": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["subject", "verb", "object", "source_text", "topics"]
            }
        }
    },
    "required": ["triples"]
}

# TOPIC_EXTRACTION_SCHEMA has been removed as topics are now
# directly integrated into the TRIPLE_EXTRACTION_PROMPT and
# CONVERSATION_TRIPLE_EXTRACTION_PROMPT.