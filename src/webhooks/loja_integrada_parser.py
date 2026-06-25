"""
Parser Loja Integrada (TOTVS).
Documentação: https://developers.lojaintegrada.com.br/

Webhook payload enviado quando status do pedido muda.
Auth: Authorization: chave <api_key> no header da requisição de ENTRADA.

Situações que indicam pagamento confirmado:
  2 = Aprovado
  3 = Em Preparação
  4 = Enviado
  5 = Entregue
  6 = Cancelado (NÃO processar)
  7 = Não Aprovado (NÃO processar)
"""

PAID_SITUATION_IDS = {2, 3, 4, 5}


def is_paid_order(payload: dict) -> bool:
    """Verifica se o pedido foi pago com base em situacao.id."""
    situacao = payload.get("situacao") or {}
    situation_id = situacao.get("id") if isinstance(situacao, dict) else situacao
    try:
        return int(situation_id) in PAID_SITUATION_IDS
    except (TypeError, ValueError):
        nome = (
            situacao.get("nome", "") if isinstance(situacao, dict) else ""
        ).lower()
        return nome in (
            "aprovado",
            "em preparação",
            "preparação",
            "enviado",
            "entregue",
        )


def extract_li_order_id(payload: dict) -> str:
    """ID único do pedido na Loja Integrada."""
    return str(payload.get("id") or payload.get("numero") or "")


def extract_li_store_key(payload: dict, headers: dict) -> str:
    """
    O store_key pode vir:
    1. No campo 'loja' do payload (alias/chave da loja)
    2. No header Authorization: chave <key>
    3. No campo 'chave' do payload
    """
    store_key = (
        payload.get("loja") or payload.get("chave") or payload.get("store_key", "")
    )
    if store_key:
        return str(store_key)
    auth = headers.get("authorization", "")
    if auth.startswith("chave "):
        return auth.replace("chave ", "").strip()
    return ""


def extract_li_signals(payload: dict) -> list[dict]:
    """Extrai sinais de identidade do payload Loja Integrada."""
    cliente = payload.get("cliente") or {}
    signals = []

    email = cliente.get("email")
    if email and "@" in email:
        signals.append({"type": "email", "value": email.strip().lower()})

    fones = cliente.get("fones") or []
    if isinstance(fones, list) and fones:
        phone = (
            fones[0].get("numero", "")
            if isinstance(fones[0], dict)
            else str(fones[0])
        )
    else:
        phone = (
            cliente.get("fone")
            or cliente.get("celular")
            or cliente.get("telefone", "")
        )

    if phone:
        signals.append({"type": "phone", "value": str(phone)})

    return signals


def extract_li_utms(payload: dict) -> dict:
    """UTMs no Loja Integrada ficam no campo 'utm' (dict) ou em campos separados."""
    utm = payload.get("utm") or {}
    if not isinstance(utm, dict):
        utm = {}

    return {
        "utm_source": utm.get("utm_source") or utm.get("source"),
        "utm_medium": utm.get("utm_medium") or utm.get("medium"),
        "utm_campaign": utm.get("utm_campaign") or utm.get("campaign"),
        "gclid": utm.get("gclid") or payload.get("gclid"),
        "fbclid": utm.get("fbclid") or payload.get("fbclid"),
    }


def extract_li_revenue(payload: dict) -> tuple[float, str]:
    """Valor total do pedido."""
    try:
        total = float(payload.get("total") or payload.get("valor_total") or "0")
    except (ValueError, TypeError):
        total = 0.0
    currency = payload.get("moeda", "BRL").upper()
    return total, currency
