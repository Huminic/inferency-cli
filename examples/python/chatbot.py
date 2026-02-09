"""Example: Simple chatbot using OpenAI GPT-4.

Run `inferency scan examples/python` to see what Inferency detects.
Inferency will flag the GPT-4 usage and suggest cheaper alternatives.
"""

from openai import OpenAI

client = OpenAI()


def chat(user_message: str) -> str:
    """Send a message and get a response."""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_message},
        ],
        max_tokens=500,
    )
    return response.choices[0].message.content


def summarize(text: str) -> str:
    """Summarize a block of text."""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Summarize the following text in 2-3 sentences."},
            {"role": "user", "content": text},
        ],
        max_tokens=200,
    )
    return response.choices[0].message.content


def classify(text: str) -> str:
    """Classify text into categories. This is a simple task — a smaller model works fine."""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": "Classify the following text as: positive, negative, or neutral. Reply with one word.",
            },
            {"role": "user", "content": text},
        ],
        max_tokens=10,
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    print(chat("What is the capital of France?"))
