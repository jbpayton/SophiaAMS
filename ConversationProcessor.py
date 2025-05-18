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
        processed_messages = 0
        failed_messages = 0
        results = []
        
        self.logger.info(f"Starting to process {total_messages} messages")
        
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
        
        # Process each message
        for i, message in enumerate(messages):
            # Skip system messages in the main processing loop
            if message['role'] == 'system':
                continue
                
            try:
                msg_start = time.time()
                role = message['role']
                content = message['content']
                
                # Get the appropriate timestamp for this message
                msg_timestamp = global_timestamp
                if message_timestamps and i in message_timestamps:
                    msg_timestamp = message_timestamps[i]
                
                # Determine the entity for this message
                msg_entity = entity_name if role == 'assistant' else 'user'
                
                # If there's a name field in the message, use that
                if 'name' in message and message['name']:
                    msg_entity = message['name']
                    
                    # Track this entity reference for later resolution
                    if role == 'user' and msg_entity != 'user':
                        entity_references['user'] = msg_entity
                    elif role == 'assistant' and msg_entity != 'assistant':
                        entity_references['assistant'] = msg_entity
                
                self.logger.info(f"Processing message {i+1}/{total_messages} from {role}")
                self.logger.debug(f"Message {i+1} content:\n---\n{content}\n---")
                
                # Create source identifier for the message
                source = f"conversation:{global_timestamp}:message:{i}:{role}"
                
                # Add message context metadata
                metadata = {
                    'conversation_timestamp': global_timestamp,
                    'message_index': i,
                    'role': role,
                    'entity': msg_entity,
                    'speaker': msg_entity  # Add explicit speaker field
                }
                
                # Process message with the memory system
                result = self.memory.ingest_text(
                    text=content,
                    source=source,
                    timestamp=msg_timestamp,
                    speaker=msg_entity  # Pass speaker to ingest_text
                )

                # Add entity and metadata to the result for our tracking
                result['entity'] = msg_entity
                result['additional_metadata'] = metadata
                
                results.append(result)
                processed_messages += 1
                
                msg_time = time.time() - msg_start
                self.logger.info(f"Successfully processed message {i+1} in {msg_time:.2f}s")
                
                # Log extracted triples
                original_extracted = result.get('original_triples', {}).get('triples', [])
                summary_extracted = result.get('summary_triples', {}).get('triples', [])
                self.logger.debug(f"Message {i+1} original triples ({len(original_extracted)}): {original_extracted}")
                self.logger.debug(f"Message {i+1} summary triples ({len(summary_extracted)}): {summary_extracted}")
                
            except Exception as e:
                failed_messages += 1
                self.logger.error(f"Error processing message {i+1}: {str(e)}")
                self.logger.debug("Error details:", exc_info=True)
                continue
        
        # Process entity references to create links between different names
        if entity_references:
            self._create_entity_reference_triples(entity_references, global_timestamp)
        
        total_time = time.time() - start_time
        self.logger.info(f"Completed processing {processed_messages}/{total_messages} messages in {total_time:.2f}s")
        
        if failed_messages:
            self.logger.warning(f"Failed to process {failed_messages} messages")
        
        # Optionally, ingest the entire conversation as a single entity
        # This could be useful for capturing the overall context
        try:
            if processed_messages > 0:
                # Create a version of the conversation with speaker information
                full_conversation_with_speakers = []
                for msg in messages:
                    if msg['role'] != 'system':
                        speaker = msg.get('name', msg['role'])
                        content = msg['content']
                        full_conversation_with_speakers.append(f"SPEAKER:{speaker}|{content}")
                
                full_conversation = "\n\n".join(full_conversation_with_speakers)
                
                # Create a summary of the conversation
                conversation_source = f"conversation:{global_timestamp}:summary"
                
                # Ingest the full conversation as a single text
                conversation_result = self.memory.ingest_text(
                    text=full_conversation,
                    source=conversation_source,
                    timestamp=global_timestamp
                )
                
                # Add entity and metadata for tracking
                conversation_result['entity'] = entity_name
                conversation_result['additional_metadata'] = {
                    'type': 'conversation_summary',
                    'entity_name': entity_name,
                    'message_count': total_messages,
                    'system_message': system_message,
                    'entity_references': entity_references
                }
                
                self.logger.info(f"Processed full conversation summary")
                
                # Add to results
                conversation_context['conversation_summary_result'] = conversation_result
        except Exception as e:
            self.logger.error(f"Error processing conversation summary: {str(e)}")
            self.logger.debug("Error details:", exc_info=True)
        
        return {
            'success': True,
            'processed_messages': processed_messages,
            'failed_messages': failed_messages,
            'total_messages': total_messages,
            'processing_time': total_time,
            'conversation_context': conversation_context,
            'results': results
        }
    
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