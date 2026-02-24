#!/bin/sh
set -e

if [ -z "$BACKEND_URL" ]; then
  echo "ERROR: BACKEND_URL environment variable is required" >&2
  exit 1
fi

CREDENTIALS_URL="${BACKEND_URL}/api/internal/credentials/perplexity"
MAX_RETRIES=60
RETRY_DELAY=30
ATTEMPT=0

echo "Waiting for Perplexity API key from backend..."

while [ "$ATTEMPT" -lt "$MAX_RETRIES" ]; do
  ATTEMPT=$((ATTEMPT + 1))

  # Fetch credentials from backend
  RESPONSE=$(curl -s -w "\n%{http_code}" "$CREDENTIALS_URL" 2>&1) || {
    echo "Attempt $ATTEMPT/$MAX_RETRIES: Failed to connect to backend at $CREDENTIALS_URL. Retrying in ${RETRY_DELAY}s..." >&2
    sleep "$RETRY_DELAY"
    continue
  }

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" = "200" ]; then
    # Extract api_key from JSON response
    API_KEY=$(echo "$BODY" | jq -r '.api_key // empty')

    if [ -n "$API_KEY" ]; then
      echo "API key retrieved successfully. Starting Perplexity MCP server..."
      export PERPLEXITY_API_KEY="$API_KEY"
      exec npm run start:http:public
    else
      echo "Attempt $ATTEMPT/$MAX_RETRIES: Failed to parse API key from response. Retrying in ${RETRY_DELAY}s..." >&2
      sleep "$RETRY_DELAY"
    fi
  elif [ "$HTTP_CODE" = "404" ]; then
    echo "Attempt $ATTEMPT/$MAX_RETRIES: No Perplexity API key configured. Retrying in ${RETRY_DELAY}s..." >&2
    sleep "$RETRY_DELAY"
  else
    echo "Attempt $ATTEMPT/$MAX_RETRIES: Unexpected response from backend (HTTP $HTTP_CODE). Retrying in ${RETRY_DELAY}s..." >&2
    sleep "$RETRY_DELAY"
  fi
done

echo "ERROR: Failed to retrieve Perplexity API key after $MAX_RETRIES attempts. Exiting." >&2
exit 1
