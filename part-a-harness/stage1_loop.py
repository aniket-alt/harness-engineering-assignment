"""Stage 1: the smallest possible agent loop (chat only, no tools yet).

The harness is just: keep a message list, send it to the model, print the reply,
append the reply, repeat. Everything later is built on this loop.
"""
import os
import sys

from openai import OpenAI

MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")

API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not API_KEY:
    sys.exit("OPENROUTER_API_KEY is missing or empty. Set it in this terminal first.")

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)

SYSTEM_PROMPT = "You are a helpful coding assistant."


def main():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Stage 1 harness | model={MODEL} | Ctrl+C or 'exit' to quit")
    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if user_input in ("exit", "quit"):
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        response = client.chat.completions.create(model=MODEL, messages=messages)
        reply = response.choices[0].message
        print(f"\nagent> {reply.content}")
        messages.append({"role": "assistant", "content": reply.content})


if __name__ == "__main__":
    main()
