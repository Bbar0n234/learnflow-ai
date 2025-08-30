FROM node:20-alpine AS builder
WORKDIR /app

# Accept build arguments for Vite environment variables
ARG VITE_ARTIFACTS_API_URL
ARG VITE_LEARNFLOW_API_URL
ENV VITE_ARTIFACTS_API_URL=$VITE_ARTIFACTS_API_URL
ENV VITE_LEARNFLOW_API_URL=$VITE_LEARNFLOW_API_URL

COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3001
CMD ["nginx", "-g", "daemon off;"]