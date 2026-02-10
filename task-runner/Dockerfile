FROM busybox:1.37-musl AS tools
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=tools /bin/busybox /usr/local/bin/cat
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/cat", "/workspace/prompt.txt"]
