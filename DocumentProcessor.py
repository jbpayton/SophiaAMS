import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import time
from urllib.parse import urlparse
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
import os
import shutil
import json
from openai import OpenAI
from utils import setup_logging
from datetime import datetime
import tiktoken

# =============================================
# Document Processing Classes
# =============================================

class DocumentSource:
    """Base class for document sources."""
    def __init__(self, uri: str):
        self.uri = uri
        self.content_type = self._detect_content_type()
    
    def _detect_content_type(self) -> str:
        """Detect the type of content based on the URI."""
        if self.uri.startswith(('http://', 'https://')):
            return 'web'
        elif self.uri.endswith('.pdf'):
            return 'pdf'
        elif self.uri.endswith('.docx'):
            return 'docx'
        else:
            return 'text'
    
    def fetch_content(self) -> Dict:
        """Fetch and process content from the source."""
        raise NotImplementedError

# Add content analysis prompt
CONTENT_ANALYSIS_PROMPT = """
Analyze this HTML content and identify the main content area. Look for:
1. The primary article/content area
2. Navigation/sidebar elements to exclude
3. Footer/header elements to exclude

Return a JSON object with:
{
    "main_content_selectors": ["list", "of", "selectors"],
    "exclude_selectors": ["list", "of", "selectors"],
    "content_type": "wiki/article/blog/etc",
    "confidence": "high/medium/low"
}

HTML content:
{content}
"""

class WebPageSource(DocumentSource):
    """Handles web page content extraction with proper chunking."""
    
    def __init__(self, uri: str, chunk_size: int = 4000, overlap: int = 500):
        super().__init__(uri)
        self.chunk_size = chunk_size  # Target token count
        self.overlap = overlap  # Token overlap between chunks
        self.content_analysis = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Initialize OpenAI client
        self.llm_client = OpenAI(
            api_key=os.getenv('LLM_API_KEY'),
            base_url=os.getenv('LLM_API_BASE')
        )
        # Initialize tokenizer
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        logging.debug(f"Initialized WebPageSource for {uri} with chunk_size={chunk_size} tokens")
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Remove common unwanted elements
        text = text.replace('\n', ' ').replace('\r', '')
        return text
    
    def _analyze_content_structure(self, soup: BeautifulSoup) -> Dict:
        """Use LLM to analyze the page structure and identify content areas."""
        try:
            logging.debug("Starting content structure analysis")
            # Extract a sample of the page (first 2000 chars) for analysis
            sample_content = str(soup)[:2000]
            
            # Get content analysis from LLM
            logging.debug("Sending content to LLM for analysis")
            response = self.llm_client.chat.completions.create(
                model=os.getenv('SUMMARIZATION_MODEL', 'gemma-3-4b-it-qat'),
                messages=[
                    {"role": "system", "content": "You are a web content analyzer. Analyze the HTML structure and identify the main content area and elements to exclude."},
                    {"role": "user", "content": CONTENT_ANALYSIS_PROMPT.format(content=sample_content)}
                ],
                temperature=0.1
            )
            
            # Parse the response
            analysis = json.loads(response.choices[0].message.content)
            logging.debug(f"Content analysis result: {json.dumps(analysis, indent=2)}")
            return analysis
            
        except Exception as e:
            logging.error(f"Error analyzing content structure: {e}")
            return {
                "main_content_selectors": [],
                "exclude_selectors": [],
                "content_type": "unknown",
                "confidence": "low"
            }
    
    def _extract_main_content(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Extract the main content area of the page using LLM analysis."""
        # First try LLM-based analysis
        if not self.content_analysis:
            self.content_analysis = self._analyze_content_structure(soup)
        
        # Try LLM-suggested selectors first
        for selector in self.content_analysis["main_content_selectors"]:
            content = soup.select_one(selector)
            if content:
                return content
        
        # Fallback to common selectors if LLM analysis didn't work
        content_selectors = [
            'main',  # HTML5 main tag
            'article',  # HTML5 article tag
            '[role="main"]',  # ARIA main role
            '#content',  # Common content ID
            '.content',  # Common content class
            '.article',  # Common article class
            '.post',  # Common blog post class
            '.entry-content',  # Common WordPress class
            '.story',  # Common news story class
            '#mw-content-text',  # MediaWiki content
            '.mw-parser-output',  # MediaWiki parser output
            '.WikiaMainContent',  # Fandom wiki content
            '.wiki-content',  # Fandom wiki content
            '.page-content',  # Fandom wiki content
        ]
        
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                return content
        
        # If no specific content area found, try to identify the main content
        # by looking for the largest text block that's not navigation/menu
        all_text_blocks = soup.find_all(['p', 'div', 'section', 'article'])
        main_content = None
        max_text_length = 0
        
        exclude_selectors = self.content_analysis["exclude_selectors"] + [
            'nav', 'header', 'footer', 'aside', '.WikiaRail', '.wiki-sidebar'
        ]
        
        for block in all_text_blocks:
            # Skip elements based on LLM analysis and common exclusions
            if any(block.find_parent(selector) for selector in exclude_selectors):
                continue
                
            text_length = len(block.get_text())
            if text_length > max_text_length:
                max_text_length = text_length
                main_content = block
        
        return main_content or soup.body
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks based on token count, avoiding duplicate content."""
        logging.debug(f"Starting text chunking. Text length: {len(text)} characters")
        
        # Tokenize the text
        tokens = self.tokenizer.encode(text)
        total_tokens = len(tokens)
        logging.debug(f"Total tokens in text: {total_tokens}")
        
        chunks = []
        start = 0
        
        while start < total_tokens:
            # Calculate end position for this chunk
            end = min(start + self.chunk_size, total_tokens)
            
            # If we're not at the end, try to find a good sentence boundary
            if end < total_tokens:
                # Look for sentence boundaries in the overlap region
                overlap_region = tokens[end-self.overlap:end]
                text_overlap = self.tokenizer.decode(overlap_region)
                
                # Find the last sentence boundary in the overlap region
                last_period = text_overlap.rfind('.')
                last_exclamation = text_overlap.rfind('!')
                last_question = text_overlap.rfind('?')
                last_newline = text_overlap.rfind('\n')
                
                # Find the last sentence boundary
                last_boundary = max(last_period, last_exclamation, last_question, last_newline)
                
                if last_boundary > 0:
                    # Adjust end position to the sentence boundary
                    boundary_tokens = self.tokenizer.encode(text_overlap[:last_boundary+1])
                    end = start + (self.chunk_size - self.overlap) + len(boundary_tokens)
            
            # Extract the chunk
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            # Clean and add the chunk
            chunk_text = self._clean_text(chunk_text)
            if chunk_text.strip():
                # Check for significant overlap with previous chunk
                if chunks:
                    prev_chunk = chunks[-1]
                    # Only keep the new content, not the overlapping part
                    overlap_start = chunk_text.find(prev_chunk[-self.overlap:])
                    if overlap_start > 0:
                        chunk_text = chunk_text[overlap_start + self.overlap:]
                        if not chunk_text.strip():
                            continue
                
                chunks.append(chunk_text)
                logging.debug(f"Created chunk {len(chunks)}: {len(chunk_tokens)} tokens, {len(chunk_text)} characters")
            
            # Move start position, accounting for overlap
            start = end - self.overlap
        
        logging.info(f"Created {len(chunks)} chunks from text, average size: {total_tokens/len(chunks):.1f} tokens per chunk")
        return chunks
    
    def fetch_content(self) -> Dict:
        """Fetch and process web page content."""
        logging.info(f"Fetching content from {self.uri}")
        try:
            # Attempt to fetch the page with timeout
            try:
                logging.debug("Making HTTP request")
                response = requests.get(self.uri, headers=self.headers, timeout=10)
                response.raise_for_status()
                logging.debug(f"HTTP response status: {response.status_code}")
            except requests.exceptions.RequestException as e:
                logging.error(f"Failed to fetch URL: {str(e)}")
                return {
                    'title': '',
                    'uri': self.uri,
                    'chunks': [],
                    'images': [],
                    'metadata': {
                        'source_type': 'web',
                        'fetch_time': time.time(),
                        'error': f"Failed to fetch URL: {str(e)}",
                        'status': 'fetch_error'
                    }
                }
            
            # Parse HTML content
            logging.debug("Parsing HTML content")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title = soup.title.string if soup.title else ''
            logging.debug(f"Extracted title: {title}")
            
            # Extract main content
            logging.debug("Starting content structure analysis")
            try:
                content_analysis = self._analyze_content_structure(soup)
                logging.debug(f"Content analysis result: {content_analysis}")
                
                # Extract main content using identified selectors
                main_content = None
                for selector in content_analysis.get('main_content_selectors', []):
                    main_content = soup.select_one(selector)
                    if main_content:
                        logging.debug(f"Found main content using selector: {selector}")
                        break
                
                if not main_content:
                    logging.warning("Could not find main content using selectors, falling back to common selectors")
                    main_content = self._extract_main_content(soup)
                
                if not main_content:
                    logging.error("Could not extract main content")
                    return {
                        'title': title,
                        'uri': self.uri,
                        'chunks': [],
                        'images': [],
                        'metadata': {
                            'source_type': 'web',
                            'fetch_time': time.time(),
                            'error': "Could not extract main content",
                            'status': 'content_error'
                        }
                    }
                
                # Extract text content
                text_content = main_content.get_text()
                logging.debug(f"Extracted text content length: {len(text_content)} characters")
                
                # Extract images
                logging.debug("Extracting images")
                images = [img.get('src') for img in main_content.find_all('img') if img.get('src')]
                logging.debug(f"Found {len(images)} images")
                
                # Chunk text content
                logging.debug("Chunking text content")
                chunks = self._chunk_text(text_content)
                logging.info(f"Created {len(chunks)} chunks from content")
                
                return {
                    'title': title,
                    'uri': self.uri,
                    'chunks': chunks,
                    'images': images,
                    'metadata': {
                        'source_type': 'web',
                        'fetch_time': time.time(),
                        'status': 'success',
                        'content_analysis': content_analysis
                    }
                }
                
            except Exception as e:
                logging.error(f"Error analyzing content structure: {str(e)}")
                # Fall back to basic content extraction
                main_content = self._extract_main_content(soup)
                if not main_content:
                    return {
                        'title': title,
                        'uri': self.uri,
                        'chunks': [],
                        'images': [],
                        'metadata': {
                            'source_type': 'web',
                            'fetch_time': time.time(),
                            'error': f"Error analyzing content: {str(e)}",
                            'status': 'analysis_error'
                        }
                    }
                
                # Extract text content
                text_content = main_content.get_text()
                logging.debug(f"Extracted text content length: {len(text_content)} characters")
                
                # Extract images
                logging.debug("Extracting images")
                images = [img.get('src') for img in main_content.find_all('img') if img.get('src')]
                logging.debug(f"Found {len(images)} images")
                
                # Chunk text content
                logging.debug("Chunking text content")
                chunks = self._chunk_text(text_content)
                logging.info(f"Created {len(chunks)} chunks from content")
                
                return {
                    'title': title,
                    'uri': self.uri,
                    'chunks': chunks,
                    'images': images,
                    'metadata': {
                        'source_type': 'web',
                        'fetch_time': time.time(),
                        'status': 'success',
                        'error': f"Used fallback content extraction: {str(e)}"
                    }
                }
            
        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            return {
                'title': '',
                'uri': self.uri,
                'chunks': [],
                'images': [],
                'metadata': {
                    'source_type': 'web',
                    'fetch_time': time.time(),
                    'error': f"Unexpected error: {str(e)}",
                    'status': 'error'
                }
            }

class DocumentProcessor:
    """Processes documents and ingests them into the semantic memory."""
    
    def __init__(self, memory: AssociativeSemanticMemory):
        self.memory = memory
        logging.debug("Initialized DocumentProcessor")
    
    def process_document(self, source: DocumentSource) -> Dict:
        """Process a document and ingest it into the semantic memory."""
        logging.info(f"Processing document from source: {source.uri}")
        content = source.fetch_content()
        
        if not content['chunks']:
            logging.warning(f"No content to process from {source.uri}")
            return {
                'success': False,
                'error': 'No content to process',
                'metadata': content['metadata']
            }
        
        results = []
        for i, chunk in enumerate(content['chunks']):
            try:
                logging.debug(f"Processing chunk {i+1}/{len(content['chunks'])}")
                # Process each chunk with the existing memory system
                result = self.memory.ingest_text(
                    text=chunk,
                    source=f"{content['uri']}#chunk_{i}",
                    timestamp=content['metadata']['fetch_time']
                )
                results.append(result)
                logging.debug(f"Successfully processed chunk {i+1}")
            except Exception as e:
                logging.error(f"Error processing chunk {i} from {content['uri']}: {e}")
                continue
        
        logging.info(f"Successfully processed {len(results)} chunks from {source.uri}")
        return {
            'success': True,
            'processed_chunks': len(results),
            'total_chunks': len(content['chunks']),
            'metadata': content['metadata'],
            'images': content['images']
        }

# =============================================
# Test Code
# =============================================

if __name__ == "__main__":
    # Set up debug logging for testing
    log_file = f"document_processor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    setup_logging(debug_mode=True, log_file=log_file)
    logging.info("Starting document processor test run")
    
    # Example test pages
    test_urls = [
        "https://blazblue.fandom.com/wiki/Ragna_the_Bloodedge",
        "https://blazblue.fandom.com/wiki/Centralfiction",
        "https://blazblue.fandom.com/wiki/Rachel_Alucard",
        "https://en.wikipedia.org/wiki/Vocaloid",
        "https://vocaloid.fandom.com/wiki/Kasane_Teto",
        "https://vocaloid.fandom.com/wiki/Hatsune_Miku"
    ]
    
    # Initialize the semantic memory
    logging.info("Initializing semantic memory")
    kgraph = VectorKnowledgeGraph(path="Test_DocumentProcessing")
    memory = AssociativeSemanticMemory(kgraph)
    processor = DocumentProcessor(memory)
    
    try:
        # Process each page
        for url in test_urls:
            logging.info(f"\nProcessing {url}...")
            source = WebPageSource(url)
            result = processor.process_document(source)
            
            if result['success']:
                logging.info(f"Successfully processed {result['processed_chunks']} chunks")
                logging.info(f"Found {len(result['images'])} images")
                
                # Test querying the processed content
                logging.info("\nTesting queries...")
                queries = [
                    "Who is Ragna the Bloodedge?",
                    "What is BlazBlue: Centralfiction?",
                    "Tell me about Rachel Alucard",
                    "What is Vocaloid?",
                    "Who is Kasane Teto?",
                    "Tell me about Hatsune Miku"
                ]
                
                for query in queries:
                    logging.info(f"\nQuery: {query}")
                    related = memory.query_related_information(query)
                    logging.info(f"Found {len(related)} related triples")
                    
                    # Print a summary of the results
                    if related:
                        logging.info("\nSummary:")
                        logging.info(memory.summarize_results(related))
            else:
                logging.error(f"Failed to process document: {result.get('error', 'Unknown error')}")
                if 'metadata' in result and 'error' in result['metadata']:
                    logging.error(f"Error details: {result['metadata']['error']}")
    
    finally:
        # Clean up
        logging.info("Cleaning up resources")
        memory.close()
        if os.path.exists("Test_DocumentProcessing"):
            shutil.rmtree("Test_DocumentProcessing")
        logging.info("Test run completed") 