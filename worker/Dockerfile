FROM node:22-slim AS runtime

ENV NODE_ENV=production

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY worker ./worker

USER node

CMD ["node", "worker/index.mjs"]
