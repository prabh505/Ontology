# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* /app/
RUN npm install

COPY frontend /app

EXPOSE 3000
CMD ["npm", "run", "dev"]
