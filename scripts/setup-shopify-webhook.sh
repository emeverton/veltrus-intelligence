#!/usr/bin/env bash
# Configura webhook orders/paid → veltrus-intelligence na loja Shopify.
# Pré-requisito: shopify store auth (abre browser OAuth).
set -euo pipefail

STORE="${SHOPIFY_STORE:-byinbz-0k.myshopify.com}"
WEBHOOK_URL="${WEBHOOK_URL:-https://intelligence.ehos.com.br/webhooks/shopify/orders/paid}"
SCOPES="${SHOPIFY_SCOPES:-read_orders,write_orders,read_customers,read_webhooks,write_webhooks}"

echo "=== Veltrus Intelligence — Shopify Webhook Setup ==="
echo "Store:  $STORE"
echo "URL:    $WEBHOOK_URL"
echo ""

echo "1. Autenticando Shopify CLI (browser OAuth)..."
shopify store auth --store "$STORE" --scopes "$SCOPES"

echo ""
echo "2. Verificando webhooks existentes..."
shopify store execute --store "$STORE" --query '
{
  webhookSubscriptions(first: 25, topics: [ORDERS_PAID]) {
    edges {
      node {
        id
        topic
        endpoint {
          __typename
          ... on WebhookHttpEndpoint { callbackUrl }
        }
      }
    }
  }
}'

echo ""
echo "3. Criando webhook ORDERS_PAID (ignora se já existir URL igual)..."
shopify store execute --store "$STORE" --query "
mutation {
  webhookSubscriptionCreate(
    topic: ORDERS_PAID
    webhookSubscription: {
      callbackUrl: \"${WEBHOOK_URL}\"
      format: JSON
    }
  ) {
    webhookSubscription {
      id
      topic
      endpoint {
        __typename
        ... on WebhookHttpEndpoint { callbackUrl }
      }
    }
    userErrors { field message }
  }
}"

echo ""
echo "4. Próximo passo manual — SHOPIFY_WEBHOOK_SECRET no VPS:"
echo "   Shopify Admin → Settings → Notifications → Webhooks"
echo "   → clique no webhook criado → copie 'Signing secret'"
echo "   → ssh root@76.13.232.175"
echo "   → nano /opt/veltrus-intelligence/.env"
echo "   → SHOPIFY_WEBHOOK_SECRET=<secret>"
echo "   → set -a && source .env && set +a && docker stack deploy -c docker-compose.yml intelligence"
echo ""
echo "5. Testar:"
echo "   curl -s https://intelligence.ehos.com.br/webhooks/shopify/recent"
