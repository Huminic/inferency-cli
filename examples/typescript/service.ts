/**
 * Example: TypeScript service using multiple providers.
 *
 * Run `inferency scan examples/typescript` to see cross-provider detection.
 */

import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";

const openai = new OpenAI();
const anthropic = new Anthropic();

interface Message {
  role: "user" | "assistant";
  content: string;
}

export async function askOpenAI(messages: Message[]): Promise<string> {
  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    messages,
    max_tokens: 1000,
  });
  return response.choices[0].message.content ?? "";
}

export async function askClaude(prompt: string): Promise<string> {
  const response = await anthropic.messages.create({
    model: "claude-3-5-sonnet-20241022",
    max_tokens: 1000,
    messages: [{ role: "user", content: prompt }],
  });
  return response.content[0].type === "text" ? response.content[0].text : "";
}

export async function expensiveAnalysis(data: string): Promise<string> {
  // Using Claude Opus for a task that Sonnet or Haiku could handle
  const response = await anthropic.messages.create({
    model: "claude-3-opus-20240229",
    max_tokens: 2000,
    messages: [
      {
        role: "user",
        content: `Analyze the following data and provide a brief summary:\n\n${data}`,
      },
    ],
  });
  return response.content[0].type === "text" ? response.content[0].text : "";
}
