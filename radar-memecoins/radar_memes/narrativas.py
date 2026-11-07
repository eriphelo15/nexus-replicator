"""Narrativas: a qué tema de actualidad se engancha cada token y qué catalizadores tiene."""

import json
import os
import re
from datetime import date

# Palabras clave por narrativa. Las de 3 letras o menos tienen que aparecer
# como palabra completa ("ai" no debe casar con "Kaiser"); las más largas
# basta con que aparezcan dentro del nombre ("chatgpt" dentro de "ChatGPTCoin").
NARRATIVAS = {
    "videojuegos": ["gta", "gta6", "grandtheft", "rockstar", "vicecity", "lucia", "jason",
                    "games", "gaming", "gamer", "playstation", "ps5", "xbox", "nintendo",
                    "switch2", "minecraft", "fortnite", "roblox", "steam", "callofduty"],
    "ia": ["ai", "agi", "gpt", "chatgpt", "openai", "claude", "anthropic", "grok", "gemini",
           "deepseek", "llm", "agent", "agents", "sora", "neural", "robot", "bot"],
    "politica": ["trump", "melania", "barron", "maga", "biden", "vance", "kamala", "obama",
                 "election", "president", "congress", "senate", "midterm", "putin", "milei",
                 "bukele", "zelensky", "freedom", "newsom", "newscum"],
    "elon": ["elon", "musk", "tesla", "spacex", "xai", "doge", "mars", "starship"],
    "celebridades": ["mrbeast", "beast", "kanye", "drake", "taylor", "swift", "kardashian",
                     "ronaldo", "messi", "neymar", "speed", "ishowspeed", "kaicenat", "tate"],
    "animales": ["dog", "doge", "cat", "pepe", "frog", "inu", "shib", "wif", "bonk", "pengu",
                 "penguin", "monkey", "ape", "hippo", "moodeng", "goat", "bear", "bull"],
    "festividades": ["halloween", "spooky", "pumpkin", "ghost", "xmas", "christmas", "santa",
                     "thanksgiving", "turkey", "newyear", "grinch"],
    # Noticias del mundo cripto (ETFs, reguladores, listados): Neartkt se colgó de la
    # noticia del ETF de NEAR. Va antes que "cripto" para no perderse en lo genérico.
    "noticias_cripto": ["etf", "sec", "blackrock", "bitwise", "grayscale", "listing",
                        "binance", "coinbase", "near", "nearpad"],
    "cripto": ["pump", "sol", "solana", "bitcoin", "btc", "eth", "moon", "gem", "100x",
               "1000x", "wagmi", "gm", "defi", "meme"],
}

RUTA_CATALIZADORES = os.path.join(os.path.dirname(__file__), "catalizadores.json")


def palabras(texto):
    # Separa también camelCase: "ChatGPTCoin" -> chat, gpt, coin
    texto = re.sub(r"([a-z])([A-Z])", r"\1 \2", texto)
    return [p for p in re.split(r"[^a-z0-9]+", texto.lower()) if p]


def clasificar(texto):
    """Narrativa del token según su nombre o símbolo, o "" si no encaja en ninguna.

    No hay que pasarle el nombre del pool ("GTA 6 Coin / SOL"): el "SOL" del par
    haría que todo casara con la narrativa cripto.
    """
    en_texto = set(palabras(texto))
    junto = "".join(c for c in texto.lower() if c.isalnum())
    for narrativa, claves in NARRATIVAS.items():
        for clave in claves:
            if (len(clave) <= 3 and clave in en_texto) or (len(clave) > 3 and clave in junto):
                return narrativa
    return ""


def catalizadores():
    try:
        with open(RUTA_CATALIZADORES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def proximo_catalizador(narrativa, hoy=None):
    """(evento, días que faltan) del próximo catalizador de la narrativa, o ("", "")."""
    hoy = hoy or date.today()
    proximos = []
    for c in catalizadores():
        if c.get("narrativa") != narrativa:
            continue
        dias = (date.fromisoformat(c["fecha"]) - hoy).days
        if dias >= -3:  # los días justo después del evento también cuentan
            proximos.append((dias, c["evento"]))
    if not proximos:
        return "", ""
    dias, evento = min(proximos)
    return evento, dias
