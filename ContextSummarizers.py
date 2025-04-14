import os

from openai import OpenAI
from ConversationLogger import ConversationFileLogger


def msgs2string(messages, start_index=0, end_index=-1):
    formatted_messages = []
    for message in messages[start_index:end_index]:
        if isinstance(message, dict) and 'content' in message:
            content = message['content']
        elif isinstance(message, str):
            content = message
        else:
            # If the message is neither a dict with 'content' nor a string,
            # attempt to convert it to a string
            content = str(message)

        formatted_messages.append(content)

    return "\n".join(formatted_messages)

def summarize_messages(client, messages, start_index, end_index):
    # Extract the specified range of messages using slice notation
    messages_to_summarize = messages[start_index:end_index]

    # Prepare the prompt for summarization
    summary_prompt = "Please provide a concise summary of the following conversation:\n\n"

    messages_string = msgs2string(messages, start_index, end_index)
    summary_prompt += messages_string

    summary_prompt += "\nSummary:"

    # Send the summarization prompt to the OpenAI API
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.5,
        max_tokens=150,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    # Extract the summary from the API response
    summary = response.choices[0].message.content.strip()

    return summary

def summarize_verbose(client, input_string, start_index, end_index):
    # Prepare the prompt for summarization
    summary_prompt = "Please provide a comprehensive and detailed analysis of the following conversation, capturing " \
                     "all the key points, important facts, topics, and the speakers' perspectives, preferences, and opinions. Include " \
                     "relevant details and examples to ensure a thorough understanding of the conversation:\n\n "

    summary_prompt += input_string

    summary_prompt += "\nComprehensive Analysis:"

    # Send the summarization prompt to the OpenAI API
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.0,
        max_tokens=1000,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    # Extract the summary from the API response
    summary = response.choices[0].message.content.strip()

    return summary


def summarize_messages_tuples_simpler(client, messages, start_index=0, end_index=-1, summarize_first=True, custom_prompt=None):
    # Convert messages to a string if it's a list
    input_text = msgs2string(messages, start_index, end_index) if isinstance(messages, list) else messages

    # Optionally summarize the input text
    if summarize_first:
        input_text = summarize_verbose(client, input_text, start_index, end_index)

    # Define the creative and simplified prompt for tuple extraction
    summary_prompt = custom_prompt if custom_prompt else '''
        You are a smart assistant. Your task is to break down a conversation into key facts. Each fact should be in the form of a tuple (topic, subject, relationship, object, source). Here’s how to do it:

        1. **Topic**: What is the general category or theme of the fact?
        2. **Subject**: Who or what is the main focus of the fact?
        3. **Relationship**: What is the connection or relationship between the subject and the object?
        4. **Object**: What is the subject connected to? (An entity, concept, or another subject)
        5. **Source**: Who provided this fact?

        Only include clear, factual information. Ignore greetings, small talk, and irrelevant details.

        **Examples**:
        ```json
        [
          {
            "topic": "Favorite anime",
            "subject": "Alice",
            "relationship": "likes",
            "object": "Naruto",
            "source": "Alice"
          },
          {
            "topic": "Anime genre",
            "subject": "Naruto",
            "relationship": "is",
            "object": "shonen anime",
            "source": "Alice"
          },
          {
            "topic": "Hobby",
            "subject": "Bob",
            "relationship": "enjoys",
            "object": "cosplaying",
            "source": "Bob"
          },
          {
            "topic": "Favorite character",
            "subject": "Alice",
            "relationship": "admires",
            "object": "Kakashi",
            "source": "Alice"
          }
        ]
        ```

        Now, extract the key facts from the following conversation and format them as a JSON array of tuples:

        '''

    # Combine the prompt with the input text
    prompt = summary_prompt + input_text + "\nTuples:"

    # Generate the response from the language model
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2048,  # Adjusted for simpler models
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    # Extract and return the summarized tuples
    summary = response.choices[0].message.content.strip()
    return summary


def summarize_messages_tuples_new(client, messages, start_index=0, end_index=-1, summarize_first=True):
    # Convert messages to a string if it's a list
    input_text = msgs2string(messages, start_index, end_index) if isinstance(messages, list) else messages

    # Optionally summarize the input text
    if summarize_first:
        input_text = summarize_verbose(client, input_text, start_index, end_index)

    # Define the prompt for tuple extraction with focused topic and simplified relationships
    summary_prompt = '''
    You are an advanced AI assistant. Your task is to extract key facts from conversations and format them as JSON objects. Each fact should be represented as a JSON object with the following fields:

    1. **"topic"**: The general category or theme of the fact.
    2. **"subject"**: The main focus or entity of the fact.
    3. **"relationship"**: The connection or relationship between the subject and the object.
    4. **"object"**: What the subject is connected to (an entity, concept, or another subject).
    5. **"source"**: The person who provided this fact.
    
    Guidelines:
    - Focus on extracting clear, factual information.
    - Ignore greetings, small talk, and irrelevant details.
    - Ensure the "relationship" field is descriptive and clearly indicates the connection between the subject and object.
    - Maintain consistency in describing relationships to ensure clarity.
    - Capture all relevant details to provide a complete picture of the conversation.
    - Avoid redundancy by consolidating similar facts into a comprehensive statement.
    - Provide specific context for ambiguous statements when possible.
    - Ensure the "object" field is precise and descriptive to avoid ambiguity.
    - Attribute the correct source for each fact to ensure accuracy.
    - If a fact is inferred rather than directly stated, ensure it is clearly supported by the conversation.
    
    Key points to emphasize:
    - Separate unrelated facts into distinct JSON objects.
    - Use concise and clear descriptions for the "relationship" field.
    - Avoid mixing topics or details within a single JSON object.
    - Ensure that subjects, relationships, and objects are coherent and make sense independently.
    - Exclude facts that are contextually irrelevant to the main topics discussed.
    - When merging related facts, ensure the new statement is comprehensive and clear.
    
    Now, extract the key facts from the following conversation and format them as a JSON array of objects:

    '''

    # Combine the prompt with the input text
    prompt = summary_prompt + input_text + "\nTuples:"

    # Generate the response from the language model
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    # Extract and return the summarized tuples
    summary = response.choices[0].message.content.strip()
    return summary


def summarize_messages_tuples(client, messages, start_index=0, end_index=-1, summarize_first=True):
    # if messages is not a list then make it a list
    if not isinstance(messages, list):
        input_text = messages
    else:
        input_text = msgs2string(messages, start_index, end_index)

    if summarize_first:
        input_text = summarize_verbose(client, input_text, start_index, end_index)


    summary_prompt = '''
    Extract factual information from the provided text as (topic, subject, relationship, object, source) tuples. Follow these guidelines:
    0. Only include factual information that can be directly extracted from the text.
    1. Focus on fundamental relationships between entities, including the preferences and opinions of the speakers.
    2. Ensure all facts are extracted as individual tuples, capturing the main points and details from the conversation.
    3. Treat the speakers as subjects when they express personal facts, preferences, opinions, or thoughts about topics or entities.
    4. Exclude conversational elements like greetings, thanks, or other exchanges that don't contribute to the main topics.
    5. Ensure that each tuple is a complete thought and doesn't require additional context.
    6. Topic should be a broad category that encompasses the subject. The topic of the conversation containing the subject.
    7. Choose an accurate relationship to convey the core meaning.
    8. The object should be a single entity or concept that is directly related to a subject and a relationship.
    9. Keep the object concise and clear, focusing on the most essential information.
    10. Use the speakers' names instead of pronouns when referring to them in the tuples.
    11. Make sure the source is the speaker's name or a referenced source.
    12. Capture inferred identities, such as the type or category of an entity (e.g., Mobile Suit Gundam is an anime).
    13. Separate objects into individual tuples when multiple objects are mentioned in relation to a subject and relationship.

    Here are a few examples of tuples:
    {
      "topic": "Favorite anime",
      "subject": "Alice",
      "relationship": "likes",
      "object": "Naruto",
      "source": "Alice"
    },
    {
      "topic": "Anime genre",
      "subject": "Naruto",
      "relationship": "is",
      "object": "shonen",
      "source": "Alice"
    },
    {
      "topic": "Hobby",
      "subject": "Bob",
      "relationship": "enjoys",
      "object": "cosplaying",
      "source": "Bob"
    },
    {
      "topic": "Favorite character",
      "subject": "Alice",
      "relationship": "admires",
      "object": "Kakashi",
      "source": "Alice"
    }

    Now, extract tuples from the following text and format the output as a JSON array of tuple objects:
    :\n\n'''

    prompt = summary_prompt + input_text

    prompt += "\nTuples:"

    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=4096,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    summary = response.choices[0].message.content.strip()

    return summary


if __name__ == "__main__":
    # Test the message summarization functions
    from util import load_secrets

    load_secrets("secrets.json")

    client = OpenAI(
        api_key="sk-111111111111111111111111111111111111111111111111",
        base_url=os.environ['LOCAL_TEXTGEN_API_BASE']
    )

    # create an empty list to store messages
    messages = []

    # use the ConversationLogger class to load the messages
    agent_logs = ConversationFileLogger("Sophia_logs")
    agent_logs.append_last_lines_to_messages(200, messages)

    start_index = -30
    end_index = -1

    original_text = msgs2string(messages, start_index, end_index)
    print("Original Text:")
    print(original_text)

    summary = summarize_messages(client, messages, start_index, end_index)
    print("Concise Summary:")
    print(summary)

    detailed_summary = summarize_verbose(client, msgs2string(messages), start_index, end_index)
    print("\nDetailed Summary:")
    print(detailed_summary)

    triples = summarize_messages_tuples(client, messages, start_index, end_index)
    print("\nExtracted Tuples (1, with summary):")
    print(triples)

    triples = summarize_messages_tuples_simpler(client, messages, start_index, end_index)
    print("\nExtracted Tuples (2, without summary):")
    print(triples)



