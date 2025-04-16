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



