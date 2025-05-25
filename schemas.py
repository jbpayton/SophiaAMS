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
                    "source_text": {"type": "string"}
                },
                "required": ["subject", "verb", "object", "source_text"]
            }
        }
    },
    "required": ["triples"]
}