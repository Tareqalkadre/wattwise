FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npx vite build || npm run build

FROM scratch AS export
COPY --from=builder /app/dist /dist
