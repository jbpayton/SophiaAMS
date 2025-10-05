"""
Streamlit test client for SophiaAMS API
Provides a chat interface to test conversation ingestion and querying
"""
import streamlit as st
import requests
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any

# Configuration
API_BASE_URL = "http://localhost:8000"

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "speaker_names" not in st.session_state:
    st.session_state.speaker_names = {"user": "User", "assistant": "Assistant"}
if "auto_retrieval_results" not in st.session_state:
    st.session_state.auto_retrieval_results = []

def make_api_request(endpoint: str, method: str = "GET", data: Dict = None) -> Dict:
    """Make API request with error handling."""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        if method == "POST":
            response = requests.post(url, json=data)
        else:
            response = requests.get(url, params=data)

        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Could not connect to API server. Make sure it's running on localhost:8000")
        return {"error": "Connection failed"}
    except requests.exceptions.RequestException as e:
        st.error(f"API request failed: {e}")
        return {"error": str(e)}

def ingest_conversation(messages: List[Dict], force_process: bool = False) -> Dict:
    """Ingest conversation to the API."""
    data = {
        "messages": messages,
        "session_id": st.session_state.session_id,
        "speaker_names": st.session_state.speaker_names,
        "force_process": force_process,
        "metadata": {
            "client": "streamlit_test",
            "timestamp": datetime.now().isoformat()
        }
    }

    result = make_api_request("/ingest/conversation", "POST", data)
    return result

def get_buffer_status() -> Dict:
    """Get conversation buffer status."""
    return make_api_request(f"/conversation/buffer/{st.session_state.session_id}")

def force_process_buffer() -> Dict:
    """Force process conversation buffer."""
    data = st.session_state.speaker_names
    return make_api_request(f"/conversation/process/{st.session_state.session_id}", "POST", data)

def query_memory(query_text: str, limit: int = 10) -> Dict:
    """Query the memory system."""
    data = {
        "text": query_text,
        "limit": limit,
        "session_id": st.session_state.session_id,
        "return_summary": True
    }

    return make_api_request("/query", "POST", data)

def get_associative_content(query_text: str, hops: int = 2) -> Dict:
    """Get associative content."""
    data = {
        "text": query_text,
        "limit": 10,
        "hops": hops
    }

    return make_api_request("/retrieve/associative", "POST", data)

# Streamlit UI
st.title("🧠 SophiaAMS Test Client")
st.sidebar.title("Controls")

# Health check
health = make_api_request("/health")
if "error" not in health:
    st.sidebar.success("✅ API Server Connected")
else:
    st.sidebar.error("❌ API Server Disconnected")

# Session info
st.sidebar.write(f"**Session ID:** `{st.session_state.session_id[:8]}...`")

# Speaker names configuration
st.sidebar.subheader("🎭 Speaker Names")
user_name = st.sidebar.text_input("User Name", value=st.session_state.speaker_names["user"])
assistant_name = st.sidebar.text_input("Assistant Name", value=st.session_state.speaker_names["assistant"])

if user_name != st.session_state.speaker_names["user"] or assistant_name != st.session_state.speaker_names["assistant"]:
    st.session_state.speaker_names = {"user": user_name, "assistant": assistant_name}
    st.sidebar.success("Speaker names updated!")

# Buffer status
st.sidebar.subheader("📦 Conversation Buffer")
buffer_status = get_buffer_status()
if "error" not in buffer_status:
    if buffer_status.get("exists", False):
        st.sidebar.metric("Buffered Messages", buffer_status.get("buffered_messages", 0))
        if buffer_status.get("should_process", False):
            st.sidebar.warning("⚠️ Buffer ready for processing")

        if st.sidebar.button("🔄 Force Process Buffer"):
            result = force_process_buffer()
            if "error" not in result:
                st.sidebar.success("✅ Buffer processed!")
            else:
                st.sidebar.error("❌ Processing failed")
    else:
        st.sidebar.info("No active buffer")

# Stats
stats = make_api_request("/stats")
if "error" not in stats:
    st.sidebar.metric("Total Triples", stats.get("total_triples", 0))

# Main interface tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Chat", "Memory Query", "Auto Memory", "Exploration", "Document Upload"])

def generate_assistant_response(prompt: str, retrieval_results: Dict = None) -> str:
    """Generate an LLM response using memory context, calling LLM directly."""
    import os
    from openai import OpenAI

    # Format memory context for the LLM
    memory_context = ""
    if retrieval_results and "error" not in retrieval_results:
        results = retrieval_results.get("results", {})
        memory_summary = results.get("summary", "")

        if memory_summary:
            memory_context = memory_summary

    # Create the conversation messages for LLM
    system_prompt = """You are a helpful AI assistant. You remember things from previous conversations and naturally reference them when relevant, just like a person would in normal conversation. Don't announce that you're recalling memories - just speak naturally."""

    messages = [{"role": "system", "content": system_prompt}]

    if memory_context:
        # Frame memory context as things you naturally remember
        messages.append({
            "role": "system",
            "content": f"Things you remember about this conversation or topic:\n\n{memory_context}"
        })

    messages.append({"role": "user", "content": prompt})

    # Call LLM directly using environment variables
    try:
        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv()

        # Create OpenAI client using your environment configuration
        client = OpenAI(
            base_url=os.getenv("LLM_API_BASE", "http://192.168.2.94:1234/v1"),
            api_key=os.getenv("LLM_API_KEY", "not-needed")
        )

        # Make the LLM call using your environment model
        response = client.chat.completions.create(
            model=os.getenv("EXTRACTION_MODEL", "gemma-3-4b-it-qat"),
            messages=messages,
            temperature=0.7,
            max_tokens=400
        )

        return response.choices[0].message.content

    except Exception as e:
        # Fallback if LLM call fails - provide a helpful error message
        return f"I'm having trouble generating a response right now. (Error: {str(e)[:50]}...)"

with tab1:
    st.header("💬 Chat Interface")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.write("Have a conversation with an AI that remembers previous discussions.")
    with col2:
        auto_retrieve = st.checkbox("🧠 Auto Memory Retrieval", value=True)

    # Display chat messages using default Streamlit chat
    for message in st.session_state.messages:
        speaker_name = st.session_state.speaker_names.get(message["role"], message["role"])

        # Handle different message types
        if message["role"] == "memory":
            # Show memory retrieval as a special message
            with st.chat_message("assistant", avatar="🧠"):
                st.write(f"💭 *Recalling relevant memories...*")
                if "results" in message:
                    with st.expander("🧠 Retrieved Information", expanded=False):
                        results = message["results"]
                        if "summary" in results:
                            st.write(f"**Summary:** {results['summary']}")
                        if "triples" in results:
                            st.write("**Facts:**")
                            for i, triple_data in enumerate(results["triples"][:3]):
                                if isinstance(triple_data, list) and len(triple_data) >= 2:
                                    triple = triple_data[0]
                                    if len(triple) >= 3:
                                        st.write(f"• {triple[0]} {triple[1]} {triple[2]}")
        else:
            with st.chat_message(message["role"]):
                st.write(f"**{speaker_name}:** {message['content']}")

    # Chat input - this will stay at the bottom
    if prompt := st.chat_input("Type your message..."):
        # 1. Add user message immediately
        user_message = {"role": "user", "content": prompt}
        st.session_state.messages.append(user_message)

        # 2. Perform memory retrieval if enabled
        retrieval_results = None
        if auto_retrieve:
            retrieval_results = query_memory(prompt, limit=10)
            if "error" not in retrieval_results and retrieval_results.get("results"):
                results = retrieval_results["results"]

                # Extract meaningful facts for display
                relevant_facts = []
                if "triples" in results:
                    for triple_data in results["triples"][:2]:  # Show top 2 facts
                        if isinstance(triple_data, list) and len(triple_data) >= 2:
                            triple = triple_data[0]
                            if len(triple) >= 3:
                                fact = f"{triple[0]} {triple[1]} {triple[2]}"
                                if len(fact) < 80:  # Keep it concise
                                    relevant_facts.append(fact)

                # Show memory retrieval with full results for expandable view
                memory_msg = {
                    "role": "memory",
                    "results": results
                }
                st.session_state.messages.append(memory_msg)

                # Store for auto memory tab
                st.session_state.auto_retrieval_results.append({
                    "query": prompt,
                    "results": retrieval_results,
                    "timestamp": datetime.now().isoformat()
                })

        # 3. Generate assistant response using memory
        assistant_content = generate_assistant_response(prompt, retrieval_results)

        # 4. Add assistant response
        assistant_message = {
            "role": "assistant",
            "content": assistant_content
        }
        st.session_state.messages.append(assistant_message)

        # 5. Ingest conversation in background
        # Get just the user and assistant messages for ingestion
        messages_for_ingestion = [msg for msg in st.session_state.messages[-3:] if msg["role"] in ["user", "assistant"]]
        if len(messages_for_ingestion) >= 2:
            result = ingest_conversation(messages_for_ingestion[-2:])
            if "error" not in result:
                if result.get("processed", False):
                    st.toast("✅ Conversation processed to memory!")
                else:
                    st.toast(f"📦 Buffered ({result.get('buffered_messages', 0)} messages)")
            else:
                st.toast("❌ Failed to ingest conversation")

        # Rerun to show all updates
        st.rerun()

with tab2:
    st.header("🔍 Memory Query")
    st.write("Query the ingested conversations and documents.")

    col1, col2 = st.columns([3, 1])
    with col1:
        query_text = st.text_input("Query:", placeholder="What did we discuss about...?")
    with col2:
        query_limit = st.number_input("Limit", min_value=1, max_value=50, value=10)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔍 Query Memory", use_container_width=True):
            if query_text:
                with st.spinner("Querying memory..."):
                    result = query_memory(query_text, query_limit)
                    if "error" not in result:
                        st.success(f"Found results for: '{query_text}'")

                        # Display summary if available
                        if "results" in result and isinstance(result["results"], dict):
                            if "summary" in result["results"]:
                                st.subheader("Summary")
                                st.write(result["results"]["summary"])

                            if "triples" in result["results"]:
                                st.subheader("Related Triples")
                                for triple in result["results"]["triples"][:5]:  # Show first 5
                                    if isinstance(triple, dict):
                                        st.write(f"• {triple.get('subject', '')} {triple.get('predicate', '')} {triple.get('object', '')}")
                        else:
                            st.json(result)
                    else:
                        st.error("Query failed")

    with col2:
        if st.button("🔗 Associative", use_container_width=True):
            if query_text:
                with st.spinner("Getting associative content..."):
                    result = get_associative_content(query_text)
                    if "error" not in result:
                        st.success("Found associative content")
                        st.json(result)

    with col3:
        if st.button("🧹 Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.rerun()

with tab3:
    st.header("🧠 Automatic Memory Retrieval")
    st.write("View memory that was automatically retrieved during conversations.")

    if st.session_state.auto_retrieval_results:
        for i, retrieval in enumerate(reversed(st.session_state.auto_retrieval_results[-10:])):  # Show last 10
            with st.expander(f"Query: '{retrieval['query'][:50]}...' - {retrieval['timestamp'][:19]}", expanded=False):
                results = retrieval["results"].get("results", {})

                col1, col2 = st.columns([2, 1])

                with col1:
                    if "summary" in results:
                        st.write(f"**Memory Summary:** {results['summary']}")

                    if "triples" in results and results["triples"]:
                        st.write("**Related Facts:**")
                        for triple_data in results["triples"]:
                            if isinstance(triple_data, list) and len(triple_data) >= 2:
                                triple, metadata = triple_data[0], triple_data[1]
                                confidence = metadata.get("confidence", 0)
                                st.write(f"• {triple[0]} {triple[1]} {triple[2]} (confidence: {confidence:.2f})")

                with col2:
                    st.json(retrieval["results"])

        if st.button("🗑️ Clear Auto Retrieval History"):
            st.session_state.auto_retrieval_results = []
            st.rerun()
    else:
        st.info("No automatic memory retrievals yet. Enable 'Auto Memory Retrieval' in the Chat tab and start a conversation!")

with tab4:
    st.header("🗺️ Knowledge Exploration")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Top Topics", use_container_width=True):
            with st.spinner("Loading topics..."):
                result = make_api_request("/explore/topics?top_k=10")
                if "error" not in result and "topics" in result:
                    st.subheader("Top Topics")
                    for topic in result["topics"]:
                        st.write(f"**{topic['topic']}** ({topic['size']} triples)")
                        for sample in topic['samples'][:2]:  # Show 2 samples
                            triple = sample[0]
                            st.write(f"  • {triple[0]} {triple[1]} {triple[2]}")

    with col2:
        if st.button("🎯 Top Entities", use_container_width=True):
            with st.spinner("Loading entities..."):
                result = make_api_request("/explore/entities?top_k=10")
                if "error" not in result and "entities" in result:
                    st.subheader("Most Connected Entities")
                    for entity in result["entities"]:
                        st.write(f"**{entity['entity']}** - {entity['connections']} connections")

    if st.button("🌐 Full Overview", use_container_width=True):
        with st.spinner("Loading overview..."):
            result = make_api_request("/explore/overview")
            if "error" not in result:
                st.subheader("Knowledge Overview")
                st.json(result)

with tab5:
    st.header("📝 Document Upload")
    st.write("Upload text files to add them to the knowledge base.")

    # File uploader
    uploaded_file = st.file_uploader(
        "Choose a text file",
        type=['txt', 'md', 'py', 'js', 'json', 'csv'],
        help="Upload .txt, .md, .py, .js, .json, or .csv files"
    )

    if uploaded_file is not None:
        # Read file content
        try:
            file_content = uploaded_file.read().decode('utf-8')
            file_name = uploaded_file.name

            col1, col2 = st.columns([3, 1])

            with col1:
                st.text_area("File Content Preview:", file_content[:500] + "..." if len(file_content) > 500 else file_content, height=200, disabled=True)

            with col2:
                st.write(f"**Filename:** {file_name}")
                st.write(f"**Size:** {len(file_content)} characters")

                if st.button("💾 Upload to Memory", use_container_width=True):
                    with st.spinner("Processing document..."):
                        # Prepare document data
                        doc_data = {
                            "text": file_content,
                            "source": file_name,
                            "metadata": {
                                "filename": file_name,
                                "upload_time": datetime.now().isoformat(),
                                "file_size": len(file_content)
                            }
                        }

                        # Send to API
                        result = make_api_request("/ingest/document", method="POST", data=doc_data)

                        if "error" not in result:
                            st.success(f"✅ Document '{file_name}' uploaded successfully!")
                            st.balloons()
                        else:
                            st.error(f"❌ Upload failed: {result['error']}")

        except UnicodeDecodeError:
            st.error("Could not read file. Please ensure it's a text file with UTF-8 encoding.")

    # Manual text input option
    st.divider()
    st.subheader("✏️ Manual Text Input")

    col1, col2 = st.columns([3, 1])

    with col1:
        manual_text = st.text_area("Enter text to add to memory:", height=150, placeholder="Type or paste text here...")

    with col2:
        source_name = st.text_input("Source name:", placeholder="e.g., notes, article, etc.")

        if st.button("💾 Add Text to Memory", use_container_width=True, disabled=not manual_text.strip()):
            with st.spinner("Processing text..."):
                doc_data = {
                    "text": manual_text,
                    "source": source_name or "manual_input",
                    "metadata": {
                        "input_method": "manual",
                        "upload_time": datetime.now().isoformat(),
                        "text_length": len(manual_text)
                    }
                }

                result = make_api_request("/ingest/document", method="POST", data=doc_data)

                if "error" not in result:
                    st.success("✅ Text added to memory successfully!")
                    st.balloons()
                else:
                    st.error(f"❌ Failed to add text: {result['error']}")

# Sidebar controls
st.sidebar.divider()
if st.sidebar.button("🔄 New Session"):
    st.session_state.session_id = str(uuid.uuid4())
    st.rerun()

if st.sidebar.button("📥 Test Document Ingest"):
    test_doc = {
        "text": "This is a test document about artificial intelligence and machine learning. It contains information about neural networks and deep learning algorithms.",
        "source": "streamlit_test",
        "metadata": {"type": "test_document", "timestamp": datetime.now().isoformat()}
    }

    result = make_api_request("/ingest/document", "POST", test_doc)
    if "error" not in result:
        st.sidebar.success("✅ Test document ingested!")
    else:
        st.sidebar.error("❌ Failed to ingest document")

# Instructions
st.sidebar.divider()
st.sidebar.markdown("""
### How to Use:
1. **Start the API server**: `python api_server.py`
2. **Chat Tab**: Have conversations that get stored
3. **Memory Query**: Search stored conversations
4. **Exploration**: Browse topics and entities
5. **Raw API**: Test endpoints directly
""")