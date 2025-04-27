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
import logging
from datetime import datetime
import tiktoken
from utils import setup_logging

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
{{
    "main_content_selectors": ["list", "of", "selectors"],
    "exclude_selectors": ["list", "of", "selectors"],
    "content_type": "wiki/article/blog/etc",
    "confidence": "high/medium/low"
}}

HTML content:
{content}
"""

class WebPageSource(DocumentSource):
    """Handles web page content extraction with proper chunking."""
    
    def __init__(self, uri: str, chunk_size: int = 1024, overlap: int = 128):
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
        # Initialize logger
        self.logger = logging.getLogger('DocumentProcessor.WebPageSource')
        self.logger.debug(f"Initialized WebPageSource for {uri} with chunk_size={chunk_size} tokens")
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        # Remove extra whitespace and normalize newlines
        text = ' '.join(text.split())
        # Remove common unwanted elements
        text = text.replace('\n', ' ').replace('\r', '')
        return text
    
    def _analyze_content_structure(self, soup: BeautifulSoup) -> Dict:
        """Use LLM to analyze the page structure and identify content areas."""
        try:
            # Extract a sample of the page (first 2000 chars) for analysis
            sample_content = str(soup)[:2000]
            
            # Get content analysis from LLM
            response = self.llm_client.chat.completions.create(
                model=os.getenv('SUMMARIZATION_MODEL', 'gemma-3-4b-it-qat'),
                messages=[
                    {"role": "system", "content": "You are a web content analyzer. Analyze the HTML structure and identify the main content area and elements to exclude."},
                    {"role": "user", "content": CONTENT_ANALYSIS_PROMPT.format(content=sample_content)}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            try:
                # Parse the response and validate it
                analysis_text = response.choices[0].message.content.strip()
                
                # Try to find JSON content within the response
                import re
                json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                else:
                    raise ValueError("No JSON content found in response")
                
                # Validate required fields
                required_fields = ['main_content_selectors', 'exclude_selectors', 'content_type', 'confidence']
                missing_fields = [field for field in required_fields if field not in analysis]
                if missing_fields:
                    raise ValueError(f"Missing required fields: {missing_fields}")
                
                return analysis
                
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse LLM response as JSON: {e}")
                raise
            
        except Exception as e:
            self.logger.error(f"Error analyzing content structure: {str(e)}")
            return {
                "main_content_selectors": [
                    'article',
                    'main',
                    '#mw-content-text',
                    '.mw-parser-output',
                    '.WikiaMainContent',
                    '.wiki-content',
                    '.page-content'
                ],
                "exclude_selectors": [
                    'nav',
                    'header',
                    'footer',
                    'aside',
                    '.WikiaRail',
                    '.wiki-sidebar'
                ],
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
        self.logger.info(f"Starting text chunking. Text length: {len(text)} characters")
        
        # Clean text before chunking to remove excess newlines
        text = self._clean_text(text)
        
        # Tokenize the text
        tokens = self.tokenizer.encode(text)
        total_tokens = len(tokens)
        
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
                    # Ensure we don't exceed total tokens
                    end = min(end, total_tokens)
            
            # Extract the chunk
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            # Clean the chunk text
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
                            # If we have no new content, move to next chunk
                            start = end
                            continue
                
                chunks.append(chunk_text)
                self.logger.info(f"Created chunk {len(chunks)}: {len(chunk_tokens)} tokens, {len(chunk_text)} characters")
            
            # Move start position, accounting for overlap
            new_start = end - self.overlap
            if new_start <= start:
                # Prevent infinite loop by ensuring we make progress
                new_start = start + 1
            start = new_start
            
            # Safety check to prevent infinite loops
            if start >= total_tokens:
                break
        
        self.logger.info(f"Created {len(chunks)} chunks from text, average size: {total_tokens/len(chunks):.1f} tokens per chunk")
        return chunks
    
    def fetch_content(self) -> Dict:
        """Fetch and process web page content."""
        self.logger.info(f"Fetching content from {self.uri}")
        try:
            # Attempt to fetch the page with timeout
            try:
                self.logger.debug("Making HTTP request")
                response = requests.get(self.uri, headers=self.headers, timeout=10)
                response.raise_for_status()
                self.logger.debug(f"HTTP response status: {response.status_code}")
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Failed to fetch URL: {str(e)}")
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
            self.logger.debug("Parsing HTML content")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title = soup.title.string if soup.title else ''
            self.logger.debug(f"Extracted title: {title}")
            
            # Extract main content
            self.logger.debug("Starting content structure analysis")
            try:
                content_analysis = self._analyze_content_structure(soup)
                self.logger.debug(f"Content analysis result: {content_analysis}")
                
                # Extract main content using identified selectors
                main_content = None
                for selector in content_analysis.get('main_content_selectors', []):
                    main_content = soup.select_one(selector)
                    if main_content:
                        self.logger.debug(f"Found main content using selector: {selector}")
                        break
                
                if not main_content:
                    self.logger.warning("Could not find main content using selectors, falling back to common selectors")
                    main_content = self._extract_main_content(soup)
                
                if not main_content:
                    self.logger.error("Could not extract main content")
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
                self.logger.debug(f"Extracted text content length: {len(text_content)} characters")
                
                # Clean text content of excess whitespace and newlines
                text_content = ' '.join(text_content.split())
                text_content = text_content.replace('\t', ' ')
                self.logger.debug(f"Cleaned text content length: {len(text_content)} characters")
                
                # Extract images
                self.logger.debug("Extracting images")
                images = [img.get('src') for img in main_content.find_all('img') if img.get('src')]
                self.logger.debug(f"Found {len(images)} images")
                
                # Chunk text content
                self.logger.debug("Chunking text content")
                chunks = self._chunk_text(text_content)
                self.logger.info(f"Created {len(chunks)} chunks from content")
                
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
                self.logger.error(f"Error analyzing content structure: {str(e)}")
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
                self.logger.debug(f"Extracted text content length: {len(text_content)} characters")
                
                # Clean text content of excess whitespace and newlines
                text_content = ' '.join(text_content.split())
                text_content = text_content.replace('\t', ' ')
                self.logger.debug(f"Cleaned text content length: {len(text_content)} characters")
                
                # Extract images
                self.logger.debug("Extracting images")
                images = [img.get('src') for img in main_content.find_all('img') if img.get('src')]
                self.logger.debug(f"Found {len(images)} images")
                
                # Chunk text content
                self.logger.debug("Chunking text content")
                chunks = self._chunk_text(text_content)
                self.logger.info(f"Created {len(chunks)} chunks from content")
                
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
            self.logger.error(f"Unexpected error: {str(e)}")
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
        self.logger = logging.getLogger('DocumentProcessor')
        self.logger.debug("Initialized DocumentProcessor")
    
    def process_document(self, source: DocumentSource) -> Dict:
        """Process a document and ingest it into the semantic memory."""
        start_time = time.time()
        self.logger.info(f"Processing document from source: {source.uri}")
        content = source.fetch_content()
        
        if not content['chunks']:
            self.logger.warning(f"No content to process from {source.uri}")
            return {
                'success': False,
                'error': 'No content to process',
                'metadata': content['metadata']
            }
        
        total_chunks = len(content['chunks'])
        processed_chunks = 0
        failed_chunks = 0
        results = []
        
        self.logger.info(f"Starting to process {total_chunks} chunks")
        for i, chunk in enumerate(content['chunks']):
            try:
                chunk_start = time.time()
                self.logger.info(f"Processing chunk {i+1}/{total_chunks} ({len(chunk)} characters)")
                # Process each chunk with the existing memory system
                result = self.memory.ingest_text(
                    text=chunk,
                    source=f"{content['uri']}#chunk_{i}",
                    timestamp=content['metadata']['fetch_time']
                )
                results.append(result)
                processed_chunks += 1
                chunk_time = time.time() - chunk_start
                self.logger.info(f"Successfully processed chunk {i+1} in {chunk_time:.2f}s")
                self.logger.debug(f"Chunk {i+1} results: {len(result.get('original_triples', {}).get('triples', []))} original triples, {len(result.get('summary_triples', {}).get('triples', []))} summary triples")
            except Exception as e:
                failed_chunks += 1
                self.logger.error(f"Error processing chunk {i+1} from {content['uri']}: {str(e)}")
                self.logger.debug("Error details:", exc_info=True)
                continue
            
            # Log progress every 25% or when processing is slow
            if (i + 1) % max(1, total_chunks // 4) == 0 or chunk_time > 10:
                progress = (i + 1) / total_chunks * 100
                elapsed = time.time() - start_time
                avg_time = elapsed / (i + 1)
                remaining = (total_chunks - (i + 1)) * avg_time
                self.logger.info(f"Progress: {progress:.1f}% ({i+1}/{total_chunks})")
                self.logger.info(f"Average processing time per chunk: {avg_time:.2f}s")
                self.logger.info(f"Estimated time remaining: {remaining:.2f}s")
        
        total_time = time.time() - start_time
        self.logger.info(f"Completed processing {processed_chunks}/{total_chunks} chunks in {total_time:.2f}s")
        if failed_chunks:
            self.logger.warning(f"Failed to process {failed_chunks} chunks")
        
        return {
            'success': True,
            'processed_chunks': processed_chunks,
            'failed_chunks': failed_chunks,
            'total_chunks': total_chunks,
            'processing_time': total_time,
            'metadata': content['metadata'],
            'images': content['images']
        }

    def export_all_triples_to_json(self, output_file: str) -> Dict:
        """Export all triples from the knowledge graph to a JSON file."""
        self.logger.info(f"Exporting all triples to {output_file}")
        start_time = time.time()
        
        try:
            # Get all triples from the knowledge graph
            all_triples = self.memory.kgraph.get_all_triples()
            
            # Create a dictionary with metadata and triples
            export_data = {
                'export_time': time.time(),
                'export_timestamp': datetime.now().isoformat(),
                'triple_count': len(all_triples),
                'triples': all_triples
            }
            
            # Write to JSON file
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"Successfully exported {len(all_triples)} triples to {output_file} in {elapsed_time:.2f}s")
            
            return {
                'success': True,
                'triple_count': len(all_triples),
                'export_time': elapsed_time
            }
            
        except Exception as e:
            self.logger.error(f"Error exporting triples to JSON: {str(e)}")
            return {
                'success': False,
                'error': str(e)
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
        total_start = time.time()
        total_processed = 0
        total_failed = 0
        
        for i, url in enumerate(test_urls, 1):
            logging.info(f"\nProcessing URL {i}/{len(test_urls)}: {url}")
            url_start = time.time()
            
            try:
                source = WebPageSource(url)
                result = processor.process_document(source)
                
                if result['success']:
                    total_processed += result['processed_chunks']
                    if result.get('failed_chunks', 0) > 0:
                        total_failed += result['failed_chunks']
                    
                    logging.info(f"Successfully processed {result['processed_chunks']} chunks")
                    logging.info(f"Found {len(result['images'])} images")
                    logging.info(f"Processing time: {result.get('processing_time', 0):.2f}s")
                    
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
                        query_start = time.time()
                        logging.info(f"\nQuery: {query}")
                        related = memory.query_related_information(query)
                        logging.info(f"Found {len(related)} related triples in {time.time() - query_start:.2f}s")
                        
                        # Print a summary of the results
                        if related:
                            summary_start = time.time()
                            logging.info("\nSummary:")
                            summary = memory.summarize_results(related)
                            logging.info(summary)
                            logging.info(f"Summary generation time: {time.time() - summary_start:.2f}s")
                            
                            # Log the retrieved triples
                            logging.info("\nRetrieved Triples:")
                            for i, triple in enumerate(related[:10]):  # Show first 10 triples
                                logging.info(f"{i+1}. Subject: {triple['subject']}")
                                logging.info(f"   Predicate: {triple['predicate']}")
                                logging.info(f"   Object: {triple['object']}")
                                logging.info(f"   Confidence: {triple.get('confidence', 'N/A')}")
                                logging.info(f"   Source: {triple.get('source', 'N/A')}")
                            
                            if len(related) > 10:
                                logging.info(f"... and {len(related) - 10} more triples")
                else:
                    total_failed += 1
                    logging.error(f"Failed to process document: {result.get('error', 'Unknown error')}")
                    if 'metadata' in result and 'error' in result['metadata']:
                        logging.error(f"Error details: {result['metadata']['error']}")
            
            except Exception as e:
                total_failed += 1
                logging.error(f"Error processing URL {url}: {str(e)}")
                logging.debug("Error details:", exc_info=True)
                continue
            
            url_time = time.time() - url_start
            logging.info(f"\nCompleted processing URL {i}/{len(test_urls)} in {url_time:.2f}s")
            
            # Log progress
            progress = i / len(test_urls) * 100
            elapsed = time.time() - total_start
            avg_time = elapsed / i
            remaining = (len(test_urls) - i) * avg_time
            logging.info(f"Overall progress: {progress:.1f}%")
            logging.info(f"Average time per URL: {avg_time:.2f}s")
            logging.info(f"Estimated time remaining: {remaining:.2f}s")
    
    finally:
        # Clean up
        total_time = time.time() - total_start
        logging.info("\nTest run summary:")
        logging.info(f"Total URLs processed: {len(test_urls)}")
        logging.info(f"Total chunks processed: {total_processed}")
        logging.info(f"Total failures: {total_failed}")
        logging.info(f"Total processing time: {total_time:.2f}s")
        logging.info(f"Average time per URL: {total_time/len(test_urls):.2f}s")
        
        # Export all triples to JSON
        export_file = f"triples_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        export_result = processor.export_all_triples_to_json(export_file)
        if export_result['success']:
            logging.info(f"Successfully exported {export_result['triple_count']} triples to {export_file}")
        else:
            logging.error(f"Failed to export triples: {export_result.get('error', 'Unknown error')}")
        
        logging.info("Cleaning up resources")
        memory.close()
        if os.path.exists("Test_DocumentProcessing"):
            shutil.rmtree("Test_DocumentProcessing")
        logging.info("Test run completed") 