/**
 * Example: Node.js app using OpenAI.
 *
 * Run `inferency scan examples/javascript` to see what Inferency detects.
 */

const OpenAI = require("openai");

const client = new OpenAI();

async function generateResponse(prompt) {
  const response = await client.chat.completions.create({
    model: "gpt-4",
    messages: [{ role: "user", content: prompt }],
    max_tokens: 500,
  });
  return response.choices[0].message.content;
}

async function cheapTask(text) {
  // This uses gpt-4o-mini — already optimized!
  const response = await client.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [
      { role: "system", content: "Extract keywords from the text. Return as comma-separated list." },
      { role: "user", content: text },
    ],
    max_tokens: 100,
  });
  return response.choices[0].message.content;
}

module.exports = { generateResponse, cheapTask };
