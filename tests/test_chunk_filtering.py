import os
import sys
import logging
import time
import json
import shutil
from datetime import datetime
import re
from typing import List, Dict

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DocumentProcessor import WebPageSource
from utils import setup_logging

def analyze_chunk_log(log_path: str) -> Dict:
    """Analyze the chunk log to extract statistics and categorize chunks."""
    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract chunk decisions
    pattern = r"Chunk (\d+): (KEEP|DISCARD) - (.*)"
    decisions = re.findall(pattern, content)
    
    # Count decisions
    total_chunks = len(decisions)
    kept = sum(1 for _, decision, _ in decisions if decision == 'KEEP')
    discarded = total_chunks - kept
    
    # Extract and categorize chunks by decision
    chunks_pattern = r"CHUNK (\d+) \((\d+) chars\) - (KEEP|DISCARD):\n-+\n(.*?)\n-+\n\n"
    chunks = re.findall(chunks_pattern, content, re.DOTALL)
    
    kept_chunks = []
    discarded_chunks = []
    
    for chunk_num, chars, decision, content in chunks:
        if decision == 'KEEP':
            kept_chunks.append((int(chunk_num), content[:200] + '...' if len(content) > 200 else content))
        else:
            discarded_chunks.append((int(chunk_num), content[:200] + '...' if len(content) > 200 else content))
    
    # Sort by chunk number
    kept_chunks.sort(key=lambda x: x[0])
    discarded_chunks.sort(key=lambda x: x[0])
    
    return {
        'total_chunks': total_chunks,
        'kept': kept,
        'discarded': discarded,
        'kept_ratio': kept / total_chunks if total_chunks > 0 else 0,
        'kept_chunks': kept_chunks,
        'discarded_chunks': discarded_chunks,
        'decisions': decisions
    }

def check_for_false_classifications(analysis: Dict) -> List[Dict]:
    """Check for potentially false classifications."""
    issues = []
    
    # Check for discarded chunks that contain substantial information
    for idx, content in analysis['discarded_chunks']:
        # Informative paragraph patterns
        if re.search(r'[A-Z][^.!?]{30,}[.!?]', content) and not re.search(r'(Retrieved|Archived from)', content):
            issues.append({
                'type': 'false_negative',
                'chunk': idx,
                'preview': content[:200] + '...' if len(content) > 200 else content,
                'reason': 'Contains informative paragraph but was discarded'
            })
    
    # Check for kept chunks that are mostly references
    for idx, content in analysis['kept_chunks']:
        # Reference patterns
        citation_markers = (
            content.count("Retrieved") + 
            content.count("Archived from") + 
            content.count(" et al") + 
            content.count("doi:") +
            content.count("ISBN")
        )
        
        # If most lines start with citation markers
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        citation_lines = sum(1 for line in lines if line.startswith('-') and ('Retrieved' in line or '. ' in line[:15]))
        
        if len(lines) > 2 and citation_lines / len(lines) > 0.7:
            issues.append({
                'type': 'false_positive',
                'chunk': idx,
                'preview': content[:200] + '...' if len(content) > 200 else content,
                'reason': f'Mostly references ({citation_lines}/{len(lines)} citation lines) but was kept'
            })
    
    return issues

def test_vocaloid_filtering():
    """Test the WebPageSource's filtering capabilities with the Vocaloid Wikipedia page."""
    # Set up logging
    log_file = f"test-output/chunk_filter_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    setup_logging(debug_mode=True, log_file=log_file)
    logging.info("Starting chunk filtering test on Vocaloid Wikipedia page")
    
    # Test URL
    test_url = "https://en.wikipedia.org/wiki/Vocaloid"
    
    try:
        # Initialize WebPageSource
        logging.info(f"Initializing WebPageSource for {test_url}")
        source = WebPageSource(test_url)
        
        # Fetch content
        logging.info("Fetching and processing content...")
        content = source.fetch_content()
        
        if not content.get('chunks'):
            logging.error("Failed to extract chunks from the page")
            return
        
        # Analyze the chunk log
        if 'chunk_log' in content:
            logging.info(f"Chunk log created at: {content['chunk_log']}")
            
            # Analyze the results
            logging.info("Analyzing chunk filtering results...")
            analysis = analyze_chunk_log(content['chunk_log'])
            
            # Print statistics
            logging.info(f"Total chunks: {analysis['total_chunks']}")
            logging.info(f"Kept chunks: {analysis['kept']} ({analysis['kept_ratio'] * 100:.1f}%)")
            logging.info(f"Discarded chunks: {analysis['discarded']}")
            
            # Check for potential classification issues
            issues = check_for_false_classifications(analysis)
            
            if issues:
                logging.warning(f"Found {len(issues)} potential classification issues:")
                for issue in issues:
                    logging.warning(f"  Chunk {issue['chunk']} - {issue['type']}: {issue['reason']}")
                    logging.warning(f"  Preview: {issue['preview']}")
            else:
                logging.info("No obvious classification issues detected")
                
            # Save the analysis
            analysis_file = f"chunk_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(analysis_file, 'w', encoding='utf-8') as f:
                # Convert to serializable format
                serializable = {
                    'total_chunks': analysis['total_chunks'],
                    'kept': analysis['kept'],
                    'discarded': analysis['discarded'],
                    'kept_ratio': analysis['kept_ratio'],
                    'kept_chunks': [{'idx': idx, 'preview': preview} for idx, preview in analysis['kept_chunks']],
                    'discarded_chunks': [{'idx': idx, 'preview': preview} for idx, preview in analysis['discarded_chunks']],
                    'decisions': [{'chunk': chunk, 'decision': decision, 'reason': reason} for chunk, decision, reason in analysis['decisions']],
                    'issues': issues
                }
                json.dump(serializable, f, indent=2, ensure_ascii=False)
            
            logging.info(f"Analysis saved to {analysis_file}")
        else:
            logging.error("No chunk log was created")
    
    except Exception as e:
        logging.error(f"Error during test: {str(e)}")
        logging.debug("Error details:", exc_info=True)
    
    logging.info("Test completed")

if __name__ == "__main__":
    test_vocaloid_filtering() 