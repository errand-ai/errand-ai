#!/bin/sh
set -e

if [ -z "$BACKEND_URL" ]; then
  echo "ERROR: BACKEND_URL environment variable is required" >&2
  exit 1
fi

CREDENTIALS_URL="${BACKEND_URL}/api/internal/credentials/perplexity"

echo "Waiting for Perplexity API key from backend..."

while true; do
  # Fetch credentials from backend
  RESPONSE=$(curl -s -w "\n%{http_code}" "$CREDENTIALS_URL" 2>&1) || {
    echo "Failed to connect to backend at $CREDENTIALS_URL. Retrying in 30s..." >&2
    sleep 30
    continue
  }
  
  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')
  
  if [ "$HTTP_CODE" = "200" ]; then
    # Extract api_key from JSON response
    API_KEY=$(echo "$BODY" | grep -o '"api_key":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$API_KEY" ]; then
      echo "API key retrieved successfully. Starting Perplexity MCP server..."
      export PERPLEXITY_API_KEY="$API_KEY"
      exec npm run start:http:public
    else
      echo "Failed to parse API key from response. Retrying in 30s..." >&2
      sleep 30
    fi
  elif [ "$HTTP_CODE" = "404" ]; then
    echo "No Perplexity API key configured. Retrying in 30s..." >&2
    sleep 30
  else
    echo "Unexpected response from backend (HTTP $HTTP_CODE). Retrying in 30s..." >&2
    sleep 30
  fi
done
