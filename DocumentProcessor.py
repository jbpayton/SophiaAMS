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
import trafilatura
from trafilatura.settings import use_config
import re
import spacy

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
    """Handles web page content extraction with proper chunking using Trafilatura."""
    
    def __init__(self, uri: str, chunk_size: int = 1024, overlap: int = 128):
        super().__init__(uri)
        self.chunk_size = chunk_size  # Target token count
        self.overlap = overlap  # Token overlap between chunks
        self.logger = logging.getLogger('DocumentProcessor.WebPageSource')
        self.logger.debug(f"Initialized WebPageSource for {uri} with chunk_size={chunk_size} tokens")
        
        # Initialize tokenizer for chunking
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Initialize spaCy for sentence splitting
        try:
            self.nlp = spacy.load("en_core_web_sm", disable=["tagger", "parser", "ner", "lemmatizer", "attribute_ruler"])
            # Keep only the sentencizer component for speed
            self.nlp.add_pipe("sentencizer")
        except OSError:
            self.logger.warning("spaCy model not found. Downloading small English model...")
            spacy.cli.download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm", disable=["tagger", "parser", "ner", "lemmatizer", "attribute_ruler"])
            self.nlp.add_pipe("sentencizer")
            
        # Configure trafilatura
        config = use_config()
        config.set("DEFAULT", "DEFAULT_OUTPUT_FORMAT", "json")
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")
        config.set("DEFAULT", "MIN_OUTPUT_SIZE", "200")
        config.set("DEFAULT", "MIN_EXTRACTED_SIZE", "200")
        
        # Create a safe filename from the URI
        self.safe_filename = self._get_safe_filename(uri)
        
    def _get_safe_filename(self, uri: str) -> str:
        """Create a safe filename from a URI."""
        # Extract hostname and path
        parsed_uri = urlparse(uri)
        hostname = parsed_uri.netloc
        path = parsed_uri.path
        
        # Remove common extensions and special characters
        path = re.sub(r'\.html$|\.htm$|\.php$|\.asp$', '', path)
        path = re.sub(r'[^\w\-_]', '_', path)
        
        # Combine hostname and path, limit length
        filename = f"{hostname}{path}"
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename
    
    def _create_chunk_log(self, title: str, text_content: str, chunks: List[str], classification_info: Optional[Dict] = None) -> str:
        """Create a detailed log of the document content and chunks."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"chunks_{self.safe_filename}_{timestamp}.txt"
        
        with open(log_filename, 'w', encoding='utf-8') as f:
            f.write(f"DOCUMENT: {self.uri}\n")
            f.write(f"TITLE: {title}\n")
            f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
            f.write(f"CHARACTER COUNT: {len(text_content)}\n")
            f.write(f"CHUNK COUNT: {len(chunks)}\n\n")
            
            # If we have classification info, add a summary
            if classification_info:
                f.write("="*80 + "\n")
                f.write("CHUNK CLASSIFICATION SUMMARY\n")
                f.write("="*80 + "\n\n")
                
                total_raw = len(classification_info)
                kept = len([c for c in classification_info.values() if c['decision'] == 'KEEP'])
                discarded = total_raw - kept
                
                f.write(f"Total Raw Chunks: {total_raw}\n")
                f.write(f"Chunks Kept: {kept}\n")
                f.write(f"Chunks Discarded: {discarded}\n\n")
                
                f.write("Classification Details:\n")
                for chunk_idx, info in classification_info.items():
                    f.write(f"Chunk {chunk_idx+1}: {info['decision']} - {info.get('reason', 'No reason provided')}\n")
                f.write("\n")
            
            f.write("="*80 + "\n")
            f.write("FULL DOCUMENT CONTENT\n")
            f.write("="*80 + "\n\n")
            f.write(text_content)
            f.write("\n\n")
            
            # If we have classification info, show all chunks with their classification
            if classification_info:
                f.write("="*80 + "\n")
                f.write("ALL CHUNKS WITH CLASSIFICATION\n")
                f.write("="*80 + "\n\n")
                
                for chunk_idx, info in classification_info.items():
                    if chunk_idx < len(info['content']):
                        chunk = info['content']
                        f.write(f"CHUNK {chunk_idx+1} ({len(chunk)} chars) - {info['decision']}:\n")
                        f.write("-"*40 + "\n")
                        f.write(chunk)
                        f.write("\n" + "-"*40 + "\n\n")
            
            f.write("="*80 + "\n")
            f.write("FILTERED CHUNKS (KEPT FOR PROCESSING)\n")
            f.write("="*80 + "\n\n")
            
            for i, chunk in enumerate(chunks, 1):
                f.write(f"CHUNK {i} ({len(chunk)} chars):\n")
                f.write("-"*40 + "\n")
                f.write(chunk)
                f.write("\n" + "-"*40 + "\n\n")
        
        return log_filename
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks respecting sentence boundaries and document structure."""
        self.logger.info(f"Starting text chunking. Text length: {len(text)} characters")
        
        # Use spaCy for sentence boundary detection
        doc = self.nlp(text)
        sentences = list(doc.sents)
        
        self.logger.debug(f"Detected {len(sentences)} sentences")
        
        # Create chunks by grouping sentences
        chunks = []
        current_chunk_sentences = []
        current_chunk_tokens = 0
        
        # Keep track of list items to try to keep them together
        in_list = False
        current_list_tokens = 0
        current_list_sentences = []
        
        for sentence in sentences:
            sent_text = sentence.text.strip()
            if not sent_text:
                continue
                
            # Count tokens in this sentence
            sent_tokens = len(self.tokenizer.encode(sent_text))
            
            # Check if this is the start of a list item
            is_list_item = bool(re.match(r'^\s*[-•*]\s+|^\s*\d+[.)]', sent_text))
            
            # If this single sentence exceeds the chunk size, we need to force-split it
            if sent_tokens > self.chunk_size:
                # First, flush any accumulated content
                if current_chunk_sentences:
                    chunk_text = ' '.join([s.text.strip() for s in current_chunk_sentences])
                    if chunk_text.strip():
                        chunks.append(chunk_text)
                    current_chunk_sentences = []
                    current_chunk_tokens = 0
                
                # Then split the long sentence
                long_sent_chunks = self._force_split_text(sent_text)
                chunks.extend(long_sent_chunks)
                continue
            
            # Handle list items - try to keep related list items together when possible
            if is_list_item:
                # Starting a new list
                if not in_list:
                    in_list = True
                    current_list_sentences = [sentence]
                    current_list_tokens = sent_tokens
                else:
                    # Continue the current list
                    current_list_sentences.append(sentence)
                    current_list_tokens += sent_tokens
                    
                # If the list is getting too big, flush it as its own chunk
                if current_list_tokens > self.chunk_size:
                    # First, add any non-list content if it exists
                    if current_chunk_sentences and current_chunk_sentences != current_list_sentences:
                        chunk_text = ' '.join([s.text.strip() for s in current_chunk_sentences])
                        if chunk_text.strip():
                            chunks.append(chunk_text)
                        current_chunk_sentences = []
                        current_chunk_tokens = 0
                    
                    # Then add the list as its own chunk
                    list_text = ' '.join([s.text.strip() for s in current_list_sentences])
                    if list_text.strip():
                        chunks.append(list_text)
                    
                    # Reset list tracking
                    in_list = False
                    current_list_sentences = []
                    current_list_tokens = 0
                    continue
                    
            # Not a list item
            else:
                # If we were in a list and now we're not, end the list context
                if in_list:
                    # Keep the list with preceding content if it fits
                    if current_chunk_tokens + current_list_tokens <= self.chunk_size:
                        current_chunk_sentences.extend(current_list_sentences)
                        current_chunk_tokens += current_list_tokens
                    else:
                        # List doesn't fit with previous content, make it its own chunk
                        if current_chunk_sentences:
                            chunk_text = ' '.join([s.text.strip() for s in current_chunk_sentences])
                            if chunk_text.strip():
                                chunks.append(chunk_text)
                        
                        list_text = ' '.join([s.text.strip() for s in current_list_sentences])
                        if list_text.strip():
                            chunks.append(list_text)
                            
                        current_chunk_sentences = []
                        current_chunk_tokens = 0
                    
                    # Reset list tracking
                    in_list = False
                    current_list_sentences = []
                    current_list_tokens = 0
            
            # Check if adding this sentence would exceed chunk size
            if current_chunk_tokens + sent_tokens > self.chunk_size and not in_list:
                # Flush the current chunk
                chunk_text = ' '.join([s.text.strip() for s in current_chunk_sentences])
                if chunk_text.strip():
                    chunks.append(chunk_text)
                current_chunk_sentences = [sentence]
                current_chunk_tokens = sent_tokens
            else:
                # If we're in a list, don't add list sentences here (they're tracked separately)
                if not (in_list and is_list_item):
                    current_chunk_sentences.append(sentence)
                    current_chunk_tokens += sent_tokens
        
        # Handle any remaining content
        if in_list and current_list_sentences:
            # If we have non-list content and the list fits with it, combine them
            if current_chunk_sentences and current_chunk_tokens + current_list_tokens <= self.chunk_size:
                current_chunk_sentences.extend(current_list_sentences)
            else:
                # Flush any existing content
                if current_chunk_sentences:
                    chunk_text = ' '.join([s.text.strip() for s in current_chunk_sentences])
                    if chunk_text.strip():
                        chunks.append(chunk_text)
                
                # Add the list as its own chunk
                list_text = ' '.join([s.text.strip() for s in current_list_sentences])
                if list_text.strip():
                    chunks.append(list_text)
                current_chunk_sentences = []
        
        # Add the final chunk if there's anything left
        if current_chunk_sentences:
            chunk_text = ' '.join([s.text.strip() for s in current_chunk_sentences])
            if chunk_text.strip():
                chunks.append(chunk_text)
        
        # Filter out any empty chunks and ensure minimum chunk size
        chunks = [chunk for chunk in chunks if chunk.strip()]
        
        # Log information about the chunks
        for i, chunk in enumerate(chunks):
            token_count = len(self.tokenizer.encode(chunk))
            self.logger.info(f"Chunk {i+1}: {token_count} tokens, {len(chunk)} characters")
        
        self.logger.info(f"Created {len(chunks)} chunks from text")
        return chunks
    
    def _split_bullets(self, text: str) -> List[str]:
        """Split a bullet point list into individual bullet points."""
        lines = text.split('\n')
        bullet_points = []
        current_bullet = []
        
        for line in lines:
            stripped = line.lstrip()
            # Check if this line starts a new bullet point
            if stripped.startswith('- ') or stripped.startswith('* ') or (stripped and stripped[0].isdigit() and stripped[1:3] in ('. ', ') ')):
                # If we have a previous bullet point, add it
                if current_bullet:
                    bullet_points.append('\n'.join(current_bullet))
                    current_bullet = []
                
                # Start a new bullet point
                current_bullet.append(line)
            else:
                # Continue the current bullet point
                if current_bullet:
                    current_bullet.append(line)
                else:
                    # This is not a bullet point, treat as its own item
                    bullet_points.append(line)
        
        # Add the last bullet point
        if current_bullet:
            bullet_points.append('\n'.join(current_bullet))
        
        return bullet_points
    
    def _split_paragraph(self, text: str) -> List[str]:
        """Split a large paragraph into smaller chunks at sentence boundaries using spaCy."""
        tokens = self.tokenizer.encode(text)
        
        # If the paragraph is small enough, return it as is
        if len(tokens) <= self.chunk_size:
            return [text]
        
        # Use spaCy to split into sentences
        doc = self.nlp(text)
        sentences = [sent.text for sent in doc.sents]
        
        # Now group sentences into chunks that respect the token limit
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for sentence in sentences:
            # Skip empty sentences
            if not sentence.strip():
                continue
                
            # Handle very long sentences that exceed chunk size on their own
            sentence_tokens = len(self.tokenizer.encode(sentence))
            
            if sentence_tokens > self.chunk_size:
                # If we have accumulated content, flush it first
                if current_chunk:
                    chunks.append(''.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                # Then split the long sentence at word boundaries
                long_sentence_chunks = self._split_long_sentence(sentence)
                chunks.extend(long_sentence_chunks)
            else:
                # If adding this sentence would exceed the chunk size, start a new chunk
                if current_tokens + sentence_tokens > self.chunk_size:
                    chunks.append(''.join(current_chunk))
                    current_chunk = [sentence]
                    current_tokens = sentence_tokens
                else:
                    # Add to the current chunk
                    current_chunk.append(sentence)
                    current_tokens += sentence_tokens
        
        # Add the final chunk if there's anything left
        if current_chunk:
            chunks.append(''.join(current_chunk))
        
        return chunks
    
    def _split_long_sentence(self, sentence: str) -> List[str]:
        """Split an extremely long sentence at word boundaries."""
        tokens = self.tokenizer.encode(sentence)
        
        # If small enough, return as is
        if len(tokens) <= self.chunk_size:
            return [sentence]
        
        # Split the sentence into words
        words = sentence.split(' ')
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for word in words:
            word_with_space = word + ' '
            word_tokens = len(self.tokenizer.encode(word_with_space))
            
            # If a single word is longer than chunk size, we have to split it
            if word_tokens > self.chunk_size:
                # Flush current chunk if any
                if current_chunk:
                    chunks.append(''.join(current_chunk).strip())
                    current_chunk = []
                    current_tokens = 0
                
                # Force split the word
                word_chunks = self._force_split_text(word)
                chunks.extend(word_chunks)
            else:
                # If adding this word would exceed chunk size, start a new chunk
                if current_tokens + word_tokens > self.chunk_size:
                    chunks.append(''.join(current_chunk).strip())
                    current_chunk = [word_with_space]
                    current_tokens = word_tokens
                else:
                    # Add to current chunk
                    current_chunk.append(word_with_space)
                    current_tokens += word_tokens
        
        # Add the final chunk if there's anything left
        if current_chunk:
            chunks.append(''.join(current_chunk).strip())
        
        return chunks
    
    def _force_split_text(self, text: str) -> List[str]:
        """Force-split text when no good boundaries are found."""
        tokens = self.tokenizer.encode(text)
        
        # If text is already small enough, return it as is
        if len(tokens) <= self.chunk_size:
            return [text]
        
        chunks = []
        for i in range(0, len(tokens), self.chunk_size):
            # Get a subset of tokens
            chunk_tokens = tokens[i:i + self.chunk_size]
            # Decode back to text
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)
        
        return chunks
    
    def _filter_chunks_with_llm(self, chunks: List[str]) -> Dict:
        """Filter chunks using LLM classification to keep only knowledge-rich content.
        
        Returns:
            Dict containing filtered chunks and classification info
        """
        filtered_chunks = []
        classification_info = {}
        
        # Initialize OpenAI client with environment variables
        client = OpenAI(
            base_url=os.getenv('LLM_API_BASE'),
            api_key=os.getenv('LLM_API_KEY'),
        )
        
        # Process chunks in batches to minimize API calls
        batch_size = 5
        
        # Pre-filter very short chunks
        chunks_to_process = []
        for i, chunk in enumerate(chunks):
            # If chunk is very short, automatically filter it out
            if len(chunk.strip()) < 100:
                classification_info[i] = {
                    'content': chunk,
                    'decision': 'DISCARD',
                    'reason': "Very short content (< 100 chars)"
                }
                self.logger.debug(f"Automatically filtering out very short chunk {i+1} ({len(chunk)} chars)")
            else:
                chunks_to_process.append((i, chunk))
                
        # Process chunks in batches
        for i in range(0, len(chunks_to_process), batch_size):
            batch = chunks_to_process[i:i+batch_size]
            
            # Prepare the prompt for the batch
            batch_texts = []
            for j, (original_idx, chunk) in enumerate(batch):
                # Truncate very long chunks to first 1000 chars for classification
                preview = chunk[:1000] + ("..." if len(chunk) > 1000 else "")
                # Add context about chunk position (e.g., if it's late in the document)
                is_late_document = original_idx > (0.75 * len(chunks))
                position_context = " (This chunk is from the end of the document)" if is_late_document else ""
                batch_texts.append(f"CHUNK {j+1}{position_context}:\n{preview}\n")
            
            # PROMPT TO BE MODIFIED BY USER
            prompt = f"""Review each text chunk. Your primary goal is to distinguish between:
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

{chr(10).join(batch_texts)}
"""

            # System message to guide the LLM's role
            messages = [
                        {"role": "system", "content": "You are a content classifier. Your task is to accurately distinguish between: 1. Informational content (which may include explanatory lists and citations that are integral to the topic) and 2. Lists that primarily serve as external references or navigation. Your goal is to KEEP the informational content and DISCARD the external reference/navigation lists."},
                        {"role": "user", "content": prompt}
                    ]

            try:
                # Call the LLM API using your configuration
                model_name = os.getenv('CLASSIFICATION_MODEL', 'gemma-3-4b-it-qat')
                self.logger.debug(f"Using model {model_name} for chunk classification")
                
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=150,
                    temperature=0
                )
                
                # Process the results
                results = response.choices[0].message.content.strip().split('\n')
                
                # Apply the results back to the batch
                for j, result in enumerate(results):
                    if j < len(batch):
                        original_idx = batch[j][0]
                        
                        # Parse decision and reason
                        if " - " in result:
                            decision_part, reason_part = result.split(" - ", 1)
                            is_keep = "KEEP" in decision_part.upper()
                            reason = reason_part.strip()
                        else:
                            # Fallback if format doesn't match
                            is_keep = "KEEP" in result.upper() and "DISCARD" not in result.upper()
                            reason = "Informational content" if is_keep else "List of references"
                        
                        classification_info[original_idx] = {
                            'content': chunks[original_idx],
                            'decision': 'KEEP' if is_keep else 'DISCARD',
                            'reason': reason
                        }
                        
                        if is_keep:
                            filtered_chunks.append(chunks[original_idx])
                        else:
                            self.logger.info(f"Filtered out chunk {original_idx+1} (length: {len(chunks[original_idx])} chars): {reason}")
            
            except Exception as e:
                # On error, default to keeping content (safety first)
                self.logger.error(f"Error during LLM classification: {str(e)}")
                self.logger.debug("Defaulting to keeping content due to error")
                
                for j, (original_idx, _) in enumerate(batch):
                    # If classification_info already has this index, skip it (e.g., very short chunks)
                    if original_idx not in classification_info:
                        classification_info[original_idx] = {
                            'content': chunks[original_idx],
                            'decision': 'KEEP',
                            'reason': "Error fallback - keeping content by default"
                        }
                        filtered_chunks.append(chunks[original_idx])
        
        # Check for chunks we missed due to indexing errors
        # This ensures all chunks get a classification, even if an error occurred or the LLM response was incomplete
        for original_chunk_index, chunk_content in enumerate(chunks):
            if original_chunk_index not in classification_info:
                classification_info[original_chunk_index] = {
                    'content': chunk_content,
                    'decision': 'KEEP',
                    'reason': "LLM processing fallback - keeping content by default"
                }
                if chunk_content not in filtered_chunks: # Avoid duplicates if already added by error fallback
                    filtered_chunks.append(chunk_content)
                self.logger.warning(f"Chunk {original_chunk_index+1} may not have been processed by LLM, keeping by default.")
        
        # Fallback if all chunks were filtered by the LLM (but not if they were all short)
        if not filtered_chunks and chunks_to_process and chunks: # Ensure there were non-short chunks to begin with
            self.logger.warning("All processable chunks were filtered out by LLM, keeping the first processable chunk as fallback")
            # Find the first chunk that wasn't pre-filtered as short
            first_processable_chunk_original_idx = -1
            first_processable_chunk_content = ""
            for idx, content in chunks_to_process:
                first_processable_chunk_original_idx = idx
                first_processable_chunk_content = content
                break
            
            if first_processable_chunk_original_idx != -1:
                filtered_chunks = [first_processable_chunk_content]
                if first_processable_chunk_original_idx in classification_info:
                    classification_info[first_processable_chunk_original_idx]['decision'] = 'KEEP'
                    classification_info[first_processable_chunk_original_idx]['reason'] = 'Fallback - all processable chunks were filtered out by LLM'
                else: # Should not happen if chunks_to_process is populated correctly
                     classification_info[first_processable_chunk_original_idx] = {
                        'content': first_processable_chunk_content,
                        'decision': 'KEEP',
                        'reason': 'Fallback - all processable chunks were filtered out by LLM (new entry)'
                    }
            elif chunks: # Fallback if all chunks were short to begin with
                self.logger.warning("All chunks were very short, keeping the first chunk as fallback")
                filtered_chunks = [chunks[0]]
                if 0 in classification_info:
                    classification_info[0]['decision'] = 'KEEP'
                    classification_info[0]['reason'] = 'Fallback - all chunks were very short'
                else:
                    classification_info[0] = {
                        'content': chunks[0],
                        'decision': 'KEEP',
                        'reason': 'Fallback - all chunks were very short (new entry)'
                    }

        return {
            'filtered_chunks': filtered_chunks,
            'classification_info': classification_info
        }

    def fetch_content(self) -> Dict:
        """Fetch and process web page content using Trafilatura."""
        self.logger.info(f"Fetching content from {self.uri}")
        
        try:
            # Use trafilatura to download and extract content
            downloaded = trafilatura.fetch_url(self.uri)
            if not downloaded:
                self.logger.error(f"Failed to fetch URL: {self.uri}")
                return {
                    'title': '',
                    'uri': self.uri,
                    'chunks': [],
                    'images': [],
                    'metadata': {
                        'source_type': 'web',
                        'fetch_time': time.time(),
                        'error': f"Failed to fetch URL: {self.uri}",
                        'status': 'fetch_error'
                    }
                }
            
            # Configure trafilatura for better content extraction
            config = use_config()
            config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")
            config.set("DEFAULT", "MIN_OUTPUT_SIZE", "200")
            config.set("DEFAULT", "MIN_EXTRACTED_SIZE", "200")
            # Add configuration to better exclude boilerplate content
            config.set("DEFAULT", "FAVOR_PRECISION", "True")
            config.set("DEFAULT", "INCLUDE_LINKS", "False")
            config.set("DEFAULT", "INCLUDE_COMMENTS", "False")
            
            # Extract content with metadata
            extracted = trafilatura.extract(downloaded, 
                                          output_format='json', 
                                          with_metadata=True,
                                          include_comments=False,
                                          include_tables=True,
                                          include_images=True,
                                          include_links=False,
                                          favor_precision=True)
            
            if not extracted:
                self.logger.error(f"Failed to extract content from {self.uri}")
                return {
                    'title': '',
                    'uri': self.uri,
                    'chunks': [],
                    'raw_chunks': [],
                    'text': '',
                    'images': [],
                    'metadata': {
                        'source_type': 'web',
                        'fetch_time': time.time(),
                        'error': "Could not extract content",
                        'status': 'content_error'
                    }
                }
            
            # Parse the JSON output
            content_data = json.loads(extracted)
            
            # Extract main text and metadata
            title = content_data.get('title', '')
            text_content = content_data.get('text', '')
            self.logger.debug(f"Extracted title: {title}")
            self.logger.info(f"Extracted text content length: {len(text_content)} characters")
            
            # Extract images
            images = []
            if 'images' in content_data:
                images = content_data['images']
            self.logger.debug(f"Found {len(images)} images")
            
            # Extract metadata
            metadata = {
                'source_type': 'web',
                'fetch_time': time.time(),
                'status': 'success',
                'author': content_data.get('author', ''),
                'date': content_data.get('date', ''),
                'hostname': content_data.get('hostname', ''),
                'categories': content_data.get('categories', []),
                'tags': content_data.get('tags', []),
                'sitename': content_data.get('sitename', '')
            }
            
            # Chunk text content
            self.logger.debug("Chunking text content")
            raw_chunks = self._chunk_text(text_content)
            self.logger.info(f"Created {len(raw_chunks)} raw chunks from content")
            
            # Filter chunks using LLM
            self.logger.info("Filtering chunks using LLM classification")
            filter_result = self._filter_chunks_with_llm(raw_chunks)
            filtered_chunks = filter_result['filtered_chunks']
            classification_info = filter_result['classification_info']
            self.logger.info(f"Retained {len(filtered_chunks)}/{len(raw_chunks)} chunks after filtering")
            
            # Create a detailed chunk log file
            chunk_log = self._create_chunk_log(title, text_content, filtered_chunks, classification_info)
            self.logger.info(f"Chunk details saved to: {chunk_log}")
            
            return {
                'title': title,
                'uri': self.uri,
                'chunks': filtered_chunks,
                'raw_chunks': raw_chunks,
                'text': text_content,
                'images': images,
                'metadata': metadata,
                'chunk_log': chunk_log,
                'classification_info': classification_info
            }
            
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            self.logger.debug("Error details:", exc_info=True)
            return {
                'title': '',
                'uri': self.uri,
                'chunks': [],
                'raw_chunks': [],
                'text': '',
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
                # --- ADDED: Log chunk content ---
                self.logger.debug(f"Chunk {i+1} text:\n---\n{chunk}\n---")
                # --------------------------------
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
                # --- ADDED: Log extracted triples ---
                original_extracted = result.get('original_triples', {}).get('triples', [])
                summary_extracted = result.get('summary_triples', {}).get('triples', [])
                self.logger.debug(f"Chunk {i+1} original triples ({len(original_extracted)}): {json.dumps(original_extracted, indent=2)}")
                self.logger.debug(f"Chunk {i+1} summary triples ({len(summary_extracted)}): {json.dumps(summary_extracted, indent=2)}")
                # ----------------------------------
                # Original log for counts (kept for reference)
                # self.logger.debug(f"Chunk {i+1} results: {len(original_extracted)} original triples, {len(summary_extracted)} summary triples")
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
        
        result = {
            'success': True,
            'processed_chunks': processed_chunks,
            'failed_chunks': failed_chunks,
            'total_chunks': total_chunks,
            'processing_time': total_time,
            'metadata': content['metadata'],
            'images': content['images']
        }
        
        # Add chunk log path if available
        if 'chunk_log' in content:
            result['chunk_log'] = content['chunk_log']
            
        return result

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
        "https://en.wikipedia.org/wiki/Vocaloid",
        "https://vocaloid.fandom.com/wiki/Kasane_Teto",
        "https://blazblue.fandom.com/wiki/Ragna_the_Bloodedge",
        "https://blazblue.fandom.com/wiki/Centralfiction",
        "https://blazblue.fandom.com/wiki/Rachel_Alucard",
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
        chunk_logs = []
        
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
                    
                    # Track chunk log files
                    if 'chunk_log' in result:
                        chunk_logs.append(result['chunk_log'])
                        logging.info(f"Chunk details saved to: {result['chunk_log']}")
                    
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
                        try:
                            query_start = time.time()
                            logging.info(f"\nQuery: {query}")
                            related = memory.query_related_information(query)
                            logging.info(f"Found {len(related)} related triples in {time.time() - query_start:.2f}s")
                            
                            # Print a summary of the results
                            if related:
                                summary_start = time.time()
                                logging.info("\nSummary:")
                                try:
                                    summary = memory.summarize_results(related)
                                    logging.info(summary)
                                    logging.info(f"Summary generation time: {time.time() - summary_start:.2f}s")
                                except Exception as e:
                                    logging.error(f"Error generating summary: {str(e)}")
                                    logging.info("Attempting to summarize with fewer triples...")
                                    
                                    # Try with just the first 5 triples if there are too many
                                    if len(related) > 8:
                                        try:
                                            limited_summary = memory.summarize_results(related[:8])
                                            logging.info("Limited summary (first 8 triples only):")
                                            logging.info(limited_summary)
                                            logging.info(f"Limited summary generation time: {time.time() - summary_start:.2f}s")
                                        except Exception as e2:
                                            logging.error(f"Error generating limited summary: {str(e2)}")
                                
                                # Log the retrieved triples
                                logging.info("\nRetrieved Triples:")
                                for i, triple in enumerate(related[:10]):  # Show first 10 triples
                                    try:
                                        # Try to access as a dictionary
                                        if isinstance(triple, dict):
                                            logging.info(f"{i+1}. Subject: {triple.get('subject', 'N/A')}")
                                            logging.info(f"   Predicate: {triple.get('predicate', 'N/A')}")
                                            logging.info(f"   Object: {triple.get('object', 'N/A')}")
                                            logging.info(f"   Confidence: {triple.get('confidence', 'N/A')}")
                                            logging.info(f"   Source: {triple.get('source', 'N/A')}")
                                        # Try to access as a tuple
                                        elif isinstance(triple, tuple):
                                            logging.info(f"{i+1}. Subject: {triple[0] if len(triple) > 0 else 'N/A'}")
                                            logging.info(f"   Predicate: {triple[1] if len(triple) > 1 else 'N/A'}")
                                            logging.info(f"   Object: {triple[2] if len(triple) > 2 else 'N/A'}")
                                            logging.info(f"   Confidence: N/A")
                                            logging.info(f"   Source: N/A")
                                        else:
                                            logging.info(f"{i+1}. Triple format unknown: {type(triple)}")
                                            logging.info(f"   Contents: {triple}")
                                    except Exception as e:
                                        logging.error(f"Error displaying triple {i+1}: {str(e)}")
                                
                                if len(related) > 10:
                                    logging.info(f"... and {len(related) - 10} more triples")
                            else:
                                logging.warning(f"No relevant information found for query: '{query}'")
                        except Exception as e:
                            logging.error(f"Error processing query '{query}': {str(e)}")
                            logging.debug("Query error details:", exc_info=True)
                            continue
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
            
            # Calculate averages and remaining time safely
            elapsed = time.time() - total_start
            if i > 0:  # Prevent division by zero
                progress = i / len(test_urls) * 100
                avg_time = elapsed / i
                remaining = (len(test_urls) - i) * avg_time
            else:
                progress = 0
                avg_time = 0
                remaining = 0
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
        
        # List all generated chunk logs
        if chunk_logs:
            logging.info("\nGenerated chunk logs:")
            for log_file in chunk_logs:
                logging.info(f"- {log_file}")
        
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