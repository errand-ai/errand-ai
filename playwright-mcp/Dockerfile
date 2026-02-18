FROM mcr.microsoft.com/playwright:v1.50.0-noble

WORKDIR /app

COPY package.json .

RUN npm install --global @playwright/mcp@0.0.28

EXPOSE 8931

CMD ["npx", "@playwright/mcp", "--port", "8931", "--host", "0.0.0.0"]
