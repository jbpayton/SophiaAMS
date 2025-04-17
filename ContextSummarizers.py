import os
import time
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

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
        model=os.getenv('SUMMARY_MODEL', 'QwQ-32B'),
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
        model=os.getenv('VERBOSE_SUMMARY_MODEL', 'QwQ-32B'),
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


class ContextSummarizers:
    def __init__(self):
        """
        Initialize the Context Summarizers.
        """
        self.client = OpenAI(
            base_url=os.getenv('LLM_API_BASE'),
            api_key=os.getenv('LLM_API_KEY'),
        )

    def generate_summary(self, text: str) -> str:
        """
        Generate a concise summary of the input text.
        
        Args:
            text: Input text to summarize
            
        Returns:
            str: Generated summary
        """
        prompt = f"""Please provide a concise summary of the following text, focusing on the key facts and relationships:

{text}

Summary:"""
        
        response = self.client.chat.completions.create(
            model=os.getenv('SUMMARY_MODEL', 'QwQ-32B'),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Lower temperature for more focused summaries
        )
        
        return response.choices[0].message.content.strip()

    def generate_verbose_summary(self, text: str) -> str:
        """
        Generate a detailed summary of the input text.
        
        Args:
            text: Input text to summarize
            
        Returns:
            str: Generated detailed summary
        """
        return summarize_verbose(self.client, text, 0, -1)


if __name__ == "__main__":
    # Test text
    test_text = """
    Hatsune Miku (初音ミク), codenamed CV01, was the first Japanese VOCALOID to be both developed and distributed by Crypton Future 
    Media, Inc.. She was initially released in August 2007 for the VOCALOID2 engine and was the first member of the Character Vocal 
    Series. She was the seventh VOCALOID overall, as well as the second VOCALOID2 vocal released to be released for the engine. Her 
    voice is provided by the Japanese voice actress Saki Fujita (藤田咲, Fujita Saki)
    """

    # Initialize summarizer
    summarizer = ContextSummarizers()

    # Test concise summarization
    print("Testing concise summarization...")
    summary = summarizer.generate_summary(test_text)
    print("\nGenerated Summary:")
    print(summary)

    # Test verbose summarization
    print("\nTesting verbose summarization...")
    detailed_summary = summarizer.generate_verbose_summary(test_text)
    print("\nDetailed Summary:")
    print(detailed_summary)



