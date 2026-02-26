FROM node:20-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/tsconfig.json frontend/next.config.mjs frontend/next-env.d.ts /app/
RUN npm install

COPY frontend/src /app/src
COPY frontend/public /app/public
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app/.next/standalone /app/
COPY --from=build /app/.next/static /app/.next/static
COPY --from=build /app/public /app/public

EXPOSE 3000
CMD ["node", "server.js"]
