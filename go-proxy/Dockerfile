FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod .
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /proxy ./cmd/server

FROM alpine:3.19
RUN apk add --no-cache ca-certificates wget
COPY --from=builder /proxy /proxy
EXPOSE 9000
CMD ["/proxy"]
