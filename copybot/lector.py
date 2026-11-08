"""Lee una transacción de Solana y dice si la cartera seguida compró o vendió un token."""

WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
ESTABLES = {USDC, USDT}


def _saldos(lista, cartera):
    out = {}
    for b in lista or []:
        if b.get("owner") == cartera:
            ui = b["uiTokenAmount"]
            out[b["mint"]] = (float(ui.get("uiAmount") or 0), int(ui.get("decimals") or 0))
    return out


def leer_operacion(tx, cartera, precio_sol):
    """Devuelve la operación o None si la transacción no es un swap de un único token.

    {"mint", "lado": "compra"|"venta", "tokens" (positivo), "antes" (tokens que tenía),
     "despues", "decimales", "usd" (valor de la operación), "t" (hora del bloque)}
    """
    if not tx or tx.get("meta") is None or tx["meta"].get("err"):
        return None
    m = tx["meta"]
    claves = [k["pubkey"] if isinstance(k, dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    sol = 0.0
    if cartera in claves:
        i = claves.index(cartera)
        sol = (m["postBalances"][i] - m["preBalances"][i]) / 1e9
    pre, post = _saldos(m.get("preTokenBalances"), cartera), _saldos(m.get("postTokenBalances"), cartera)
    delta = {k: post.get(k, (0, 0))[0] - pre.get(k, (0, 0))[0] for k in set(pre) | set(post)}
    sol += delta.pop(WSOL, 0.0)
    estable = sum(delta.pop(k, 0.0) for k in ESTABLES)
    tokens = {k: v for k, v in delta.items() if v != 0}
    if len(tokens) != 1:
        return None
    mint, d = next(iter(tokens.items()))
    usd = estable + sol * precio_sol
    # Un swap: el token y el dinero se mueven en sentidos opuestos.
    if usd == 0 or (usd > 0) == (d > 0):
        return None
    decimales = (post.get(mint) or pre.get(mint))[1]
    return {"mint": mint, "lado": "compra" if d > 0 else "venta", "tokens": abs(d),
            "antes": pre.get(mint, (0, 0))[0], "despues": post.get(mint, (0, 0))[0],
            "decimales": decimales, "usd": abs(usd), "t": tx.get("blockTime")}
