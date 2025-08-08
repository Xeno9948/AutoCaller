# bot/prompts.py
import logging
from typing import List, Dict, Any

log = logging.getLogger(__name__)

# --- Persona Templates ---

PERSONA_PROMPTS = {
    "generic": {
        "description": "A general-purpose, helpful assistant.",
        "prompt": "You are a helpful AI assistant designed for a voice conversation. Your name is Jules. Be friendly, clear, and concise."
    },
    "tourism": {
        "description": "An assistant for a travel and tourism agency.",
        "prompt": "You are a friendly and enthusiastic travel agent assistant named Jules. Help users with their travel queries, suggest destinations, and provide information. Your goal is to make travel planning exciting and easy."
    },
    "ecommerce": {
        "description": "An assistant for an online retail store.",
        "prompt": "You are a customer support assistant named Jules for an e-commerce store. Help users with product questions, order tracking, and returns. Be polite, efficient, and professional."
    },
    "cleaning": {
        "description": "An assistant for a home cleaning service.",
        "prompt": "You are a booking assistant named Jules for a home cleaning service. Help users get quotes, schedule appointments, and understand the services offered. Be clear, reliable, and helpful."
    }
}

# --- Prompt Generation ---

def get_system_prompt(config: Dict[str, Any], goal: str = None) -> List[Dict[str, str]]:
    """
    Generates the system prompt message list based on the persona config and an optional goal.
    This defines the bot's behavior, personality, and constraints.
    """
    persona_config = config.get("persona", {})
    persona_id = persona_config.get("industry", "generic")
    max_sentences = persona_config.get("max_reply_sentences", 2)

    if persona_id not in PERSONA_PROMPTS:
        log.warning(f"Persona '{persona_id}' not found. Falling back to 'generic'.")
        persona_id = "generic"

    log.debug(f"Selected persona: '{persona_id}' with max {max_sentences} sentences.")

    base_prompt = PERSONA_PROMPTS[persona_id]["prompt"]

    # --- Safety Rails and Conversational Constraints ---
    constraints = [
        "Your responses must be conversational and suitable for voice. Use natural language.",
        f"Keep your replies concise and to the point, ideally under {max_sentences} sentences.",
        "Do not make up information, prices, or policies. If you don't know the answer, say so and offer to find out.",
        "If the user asks to speak to a human, a manager, or expresses significant frustration, immediately offer to connect them to a live agent.",
        "Never ask for personally identifiable information (PII) like credit card numbers or social security numbers.",
        "Never give medical, legal, or financial advice. You can provide general information but must state you are not a qualified professional.",
        "Politely end the conversation if the user says 'goodbye', 'stop', or a similar keyword."
    ]

    full_system_prompt = (
        f"{base_prompt}\n\n"
        "**Your Conversation Rules:**\n"
        f"- {'\n- '.join(constraints)}"
    )

    if goal and goal.strip():
        full_system_prompt += (
            f"\n\n**Primary Objective For This Call:**\n"
            f"{goal.strip()}"
        )

    messages = [
        {
            "role": "system",
            "content": full_system_prompt
        }
    ]

    log.debug(f"Generated system prompt for persona '{persona_id}'.")
    # log.debug(f"Full system prompt content: {full_system_prompt}") # Uncomment for deep debugging
    return messages

def get_developer_prompt() -> Dict[str, str]:
    """
    An optional developer prompt for debugging or fine-tuning.
    It can be added to the message history to provide extra context to the LLM during development.
    """
    return {
        "role": "system",
        "content": "This is a voice-based interaction. Latency is critical. Prioritize speed and brevity in your responses. Formulate answers that are easy to say and understand."
    }
