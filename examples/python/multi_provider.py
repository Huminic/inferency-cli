"""Example: Using multiple AI providers in one project.

Run `inferency report examples/python` to see optimization recommendations.
"""

from openai import OpenAI
import anthropic

openai_client = OpenAI()
anthropic_client = anthropic.Anthropic()


def generate_with_openai(prompt: str) -> str:
    """Use OpenAI for generation."""
    response = openai_client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
    )
    return response.choices[0].message.content


def generate_with_claude(prompt: str) -> str:
    """Use Anthropic Claude for generation."""
    response = anthropic_client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def quick_task(text: str) -> str:
    """A simple extraction task — using an expensive model unnecessarily."""
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Extract the email address from the text. Reply with just the email."},
            {"role": "user", "content": text},
        ],
        max_tokens=50,
    )
    return response.choices[0].message.content
