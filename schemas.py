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
                            "properties": {"type": "object"}
                        },
                        "required": ["text", "properties"]
                    },
                    "verb": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "properties": {"type": "object"}
                        },
                        "required": ["text", "properties"]
                    },
                    "object": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "properties": {"type": "object"}
                        },
                        "required": ["text", "properties"]
                    },
                    "source_text": {"type": "string"}
                },
                "required": ["subject", "verb", "object", "source_text"]
            }
        }
    },
    "required": ["triples"]
} 