import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

class ConversationProcessor:
    """Processes conversation history and ingests it into the semantic memory."""
    
    def __init__(self, memory, logger_name="ConversationProcessor"):
        """
        Initialize a ConversationProcessor.
        
        Args:
            memory: An instance of AssociativeSemanticMemory
            logger_name: Name for the logger
        """
        self.memory = memory
        self.logger = logging.getLogger(logger_name)
        self.logger.debug("Initialized ConversationProcessor")
    
    def process_conversation(self, 
                            messages: List[Dict[str, str]], 
                            entity_name: str = "assistant",
                            timestamp: Optional[float] = None,
                            message_timestamps: Optional[Dict[int, float]] = None) -> Dict:
        """
        Process a conversation and ingest it into the semantic memory.
        
        Args:
            messages: List of message dictionaries in OpenAI format with 'role' and 'content' keys
            entity_name: The entity name to associate memories with (defaults to "assistant")
            timestamp: Global timestamp for the entire conversation (defaults to current time)
            message_timestamps: Dictionary mapping message indices to individual timestamps
            
        Returns:
            Dict containing processing results
        """
        start_time = time.time()
        self.logger.info(f"Processing conversation for entity: {entity_name}")
        
        if not messages:
            self.logger.warning("No messages to process")
            return {
                'success': False,
                'error': 'No messages to process',
                'metadata': {
                    'entity_name': entity_name,
                    'timestamp': timestamp or time.time()
                }
            }
        
        # Use provided timestamp or current time
        global_timestamp = timestamp or time.time()
        
        total_messages = len(messages)
        self.logger.info(f"Starting to process conversation with {total_messages} messages")
        
        # Extract system message if present
        system_message = None
        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
                break
        
        # Track conversation context
        conversation_context = {
            'entity_name': entity_name,
            'timestamp': global_timestamp,
            'system_message': system_message,
            'message_count': total_messages
        }
        
        # Track entity names for reference resolution
        entity_references = {}
        
        # First, combine all messages with speaker information
        combined_text = ""
        filtered_messages = []
        
        for i, message in enumerate(messages):
            # Skip system messages
            if message['role'] == 'system':
                continue
                
            # Determine the entity for this message
            role = message['role']
            content = message['content']
            msg_entity = entity_name if role == 'assistant' else 'user'
            
            # If there's a name field in the message, use that
            if 'name' in message and message['name']:
                msg_entity = message['name']
                
                # Track this entity reference for later resolution
                if role == 'user' and msg_entity != 'user':
                    entity_references['user'] = msg_entity
                elif role == 'assistant' and msg_entity != 'assistant':
                    entity_references['assistant'] = msg_entity
            
            # Format the message with speaker information
            formatted_message = f"SPEAKER:{msg_entity}|{content}\n\n"
            combined_text += formatted_message
            
            # Keep track of the filtered messages
            filtered_messages.append({
                'index': i,
                'role': role,
                'content': content,
                'entity': msg_entity,
                'timestamp': message_timestamps.get(i, global_timestamp) if message_timestamps else global_timestamp
            })
        
        # Process the entire conversation at once
        try:
            source = f"conversation:{global_timestamp}:complete"
            
            # Process combined text with the memory system
            result = self.memory.ingest_text(
                text=combined_text,
                source=source,
                timestamp=global_timestamp
            )
            
            # Add metadata to the result
            result['success'] = True
            result['filtered_messages'] = filtered_messages
            result['entity_references'] = entity_references
            result['conversation_context'] = conversation_context
            result['processed_messages'] = len(filtered_messages)
            result['processing_time'] = time.time() - start_time
            
            # Log extracted triples
            original_extracted = result.get('original_triples', {}).get('triples', [])
            summary_extracted = result.get('summary_triples', {}).get('triples', [])
            self.logger.info(f"Processed {len(filtered_messages)} messages in {result['processing_time']:.2f}s")
            self.logger.debug(f"Conversation original triples ({len(original_extracted)}): {original_extracted}")
            self.logger.debug(f"Conversation summary triples ({len(summary_extracted)}): {summary_extracted}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing conversation: {str(e)}")
            self.logger.debug("Error details:", exc_info=True)
            
            return {
                'success': False,
                'error': str(e),
                'metadata': conversation_context,
                'processing_time': time.time() - start_time
            }
        
        # Process entity references to create links between different names
        if entity_references:
            self._create_entity_reference_triples(entity_references, global_timestamp)
    
    def query_conversation_memory(self, query: str, entity_name: str = None, 
                                 limit: int = 10, min_confidence: float = 0.6,
                                 speaker: str = None) -> Dict:
        """
        Query the semantic memory for conversation-related information.
        
        Args:
            query: The query to find related information
            entity_name: Optional entity name to filter results (if None, get all)
            limit: Maximum number of triples to return
            min_confidence: Minimum confidence score for triples
            speaker: Optional speaker name to filter results
            
        Returns:
            Dict containing query results
        """
        self.logger.info(f"Querying conversation memory: '{query}'")
        
        start_time = time.time()
        
        try:
            # Query the memory system
            related = self.memory.query_related_information(
                text=query,
                include_summary_triples=True
            )
            
            # Filtered results list
            filtered_related = []
            
            # Apply filters
            for triple, metadata in related:
                # Check entity filter if specified
                if entity_name:
                    triple_entity = metadata.get('entity', '')
                    if triple_entity != entity_name and triple_entity:
                        continue
                
                # Check speaker filter if specified
                if speaker:
                    triple_speaker = metadata.get('speaker', '')
                    if triple_speaker != speaker and triple_speaker:
                        continue
                
                # Entry passed all filters
                filtered_related.append((triple, metadata))
            
            # Use filtered results
            related = filtered_related
            
            # Log filter results
            if entity_name:
                self.logger.info(f"Filtered to {len(related)} triples matching entity '{entity_name}'")
            if speaker:
                self.logger.info(f"Filtered to {len(related)} triples from speaker '{speaker}'")
            
            query_time = time.time() - start_time
            self.logger.info(f"Found {len(related)} related triples in {query_time:.2f}s")
            
            # Generate a summary if results were found
            summary = None
            if related:
                try:
                    summary = self.memory.summarize_results(related)
                    self.logger.info(f"Generated summary of results")
                except Exception as e:
                    self.logger.error(f"Error generating summary: {str(e)}")
            
            return {
                'success': True,
                'query': query,
                'entity_name': entity_name,
                'speaker': speaker,
                'triples': related,
                'triple_count': len(related),
                'summary': summary,
                'query_time': query_time
            }
            
        except Exception as e:
            self.logger.error(f"Error querying conversation memory: {str(e)}")
            return {
                'success': False,
                'query': query,
                'entity_name': entity_name,
                'error': str(e),
                'query_time': time.time() - start_time
            }

    def _create_entity_reference_triples(self, entity_references: Dict[str, str], timestamp: float):
        """
        Create reference triples that link different names for the same entity.
        For example, if "user" is actually "Alex", create a triple (user, refers_to, Alex).
        
        Args:
            entity_references: Dictionary mapping generic entities to specific names
            timestamp: Timestamp for the triples
        """
        self.logger.info(f"Creating entity reference triples: {entity_references}")
        
        triples = []
        metadata_list = []
        
        for generic_entity, specific_name in entity_references.items():
            triple = (generic_entity, "refers_to", specific_name)
            triples.append(triple)
            
            # Create metadata
            metadata = {
                "source": f"entity_resolution:{timestamp}",
                "timestamp": timestamp,
                "is_from_summary": False,
                "subject_properties": {},
                "verb_properties": {},
                "object_properties": {},
                "source_text": f"{generic_entity} refers to {specific_name}",
                "speaker": "system"
            }
            metadata_list.append(metadata)
            
            # Also create the reverse mapping
            triple_reverse = (specific_name, "is_referenced_by", generic_entity)
            triples.append(triple_reverse)
            
            # Create metadata for reverse mapping
            metadata_reverse = {
                "source": f"entity_resolution:{timestamp}",
                "timestamp": timestamp,
                "is_from_summary": False,
                "subject_properties": {},
                "verb_properties": {},
                "object_properties": {},
                "source_text": f"{specific_name} is referenced by {generic_entity}",
                "speaker": "system"
            }
            metadata_list.append(metadata_reverse)
        
        # Add the triples to the knowledge graph
        if triples:
            self.memory.kgraph.add_triples(triples, metadata_list)
            self.logger.info(f"Added {len(triples)} entity reference triples")

# Example usage
if __name__ == "__main__":
    # This code would run if the file is executed directly
    # Set up logging for testing
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Example conversation in OpenAI format
    example_messages = [
        {"role": "system", "content": "You are a helpful assistant named Sophia."},
        {"role": "user", "content": "My name is Alex. Can you help me with my math homework?"},
        {"role": "assistant", "content": "Hello Alex! I'd be happy to help with your math homework. What specific problem are you working on?"},
        {"role": "user", "content": "I'm struggling with quadratic equations."},
        {"role": "assistant", "content": "I understand quadratic equations can be challenging. Let's break it down step by step. A quadratic equation has the form ax² + bx + c = 0. Would you like me to explain how to solve these using different methods?"}
    ]
    
    # You would need to initialize AssociativeSemanticMemory here
    # For example:
    # from AssociativeSemanticMemory import AssociativeSemanticMemory
    # from VectorKnowledgeGraph import VectorKnowledgeGraph
    #
    # kgraph = VectorKnowledgeGraph(path="Test_ConversationProcessing")
    # memory = AssociativeSemanticMemory(kgraph)
    # processor = ConversationProcessor(memory)
    # 
    # # Process the conversation
    # result = processor.process_conversation(
    #     messages=example_messages,
    #     entity_name="Sophia"
    # )
    # 
    # # Query for related information
    # query_result = processor.query_conversation_memory(
    #     query="What did Alex ask help with?",
    #     entity_name="Sophia"
    # )
    # 
    # print(f"Found {len(query_result['triples'])} related memories")
    # if query_result['summary']:
    #     print(f"Summary: {query_result['summary']}") 