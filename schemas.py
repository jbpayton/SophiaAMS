TRIPLE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "modifiers": {"type": "object"}
                        },
                        "required": ["text", "modifiers"]
                    },
                    "verb": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "modifiers": {"type": "object"}
                        },
                        "required": ["text", "modifiers"]
                    },
                    "object": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "modifiers": {"type": "object"}
                        },
                        "required": ["text", "modifiers"]
                    },
                    "source_text": {"type": "string"}
                },
                "required": ["subject", "verb", "object", "source_text"]
            }
        }
    },
    "required": ["triples"]
} 