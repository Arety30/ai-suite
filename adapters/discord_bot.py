"""Discord adapter (optional) — a thin client that forwards messages to the local
gateway. All AI runs locally; Discord is just a chat surface.

This is the ONLY component that touches an external network, and only to reach
Discord's gateway. It needs a bot token, which is the bot's *identity* (not an AI
API key) and is read from the environment — never hardcoded, unlike the old bots:

    export DISCORD_TOKEN=...            # from the Discord developer portal
    python adapters/discord_bot.py

If you want a 100% offline setup, use the web UI (http://127.0.0.1:8100/) or the
CLI instead and skip this adapter entirely.
"""
from __future__ import annotations

import os

import httpx

GATEWAY = os.environ.get("SUITE_GATEWAY", "http://127.0.0.1:8100")


def main() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN in the environment to run this adapter.")
    try:
        import discord
    except ImportError:
        raise SystemExit("pip install discord.py to use the Discord adapter.")

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Abrar AI Hub adapter connected as {client.user}")

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return
        if client.user in message.mentions or isinstance(
            message.channel, discord.DMChannel
        ):
            prompt = message.content.replace(f"<@{client.user.id}>", "").strip()
            async with message.channel.typing():
                async with httpx.AsyncClient(timeout=180) as http:
                    r = await http.post(
                        f"{GATEWAY}/v1/chat",
                        json={"conversation_id": message.channel.id, "message": prompt},
                    )
                reply = r.json().get("text", "[no response]")
            for i in range(0, len(reply), 1900):  # Discord's 2000-char limit
                await message.channel.send(reply[i:i + 1900])

    client.run(token)


if __name__ == "__main__":
    main()
