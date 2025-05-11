# SophiaAMS
Memory System for LLM Based Agents

## About

SophiaAMS (Associative Memory System) is a framework for processing, ingesting, and retrieving information for LLM-based agents. It features advanced document processing capabilities, knowledge graph integration, and semantic memory retrieval.

## Features

- **Document Processing**: Automatic extraction and chunking of web content using Trafilatura and spaCy
- **Knowledge Graph Integration**: Converts information into triples stored in a vector knowledge graph
- **Semantic Query**: Retrieves related information based on semantic similarity
- **Multi-Format Support**: Works with web pages, PDFs, and plain text documents

## Installation

### Quick Installation

The easiest way to install SophiaAMS is using the install script:

```bash
python install.py
```

This will:
1. Install all required Python dependencies
2. Download the necessary spaCy language model

### Manual Installation

If you prefer manual installation:

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install the spaCy English language model:
   ```bash
   python -m spacy download en_core_web_sm
   ```

## Usage

Process a web page and ingest it into the semantic memory:

```python
from DocumentProcessor import WebPageSource, DocumentProcessor
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph

# Initialize the memory system
kgraph = VectorKnowledgeGraph(path="knowledge_base")
memory = AssociativeSemanticMemory(kgraph)
processor = DocumentProcessor(memory)

# Process a document from a URL
source = WebPageSource("https://example.com/article")
result = processor.process_document(source)

# Query related information
info = memory.query_related_information("your query here")
summary = memory.summarize_results(info)
print(summary)
```

## Dependencies

Main dependencies include:
- `trafilatura`: Extracts main content from web pages
- `spacy`: Natural language processing for sentence splitting
- `tiktoken`: Tokenization for LLM-compatible chunking
- `sentence-transformers`: Embedding generation for semantic search
- `qdrant-client`: Vector database for knowledge storage
