FROM alpine:3.22

COPY run.sh /usr/local/bin/run-skeleton-worker
RUN chmod +x /usr/local/bin/run-skeleton-worker

ENV WORKER_NAME=skeleton-worker
CMD ["/usr/local/bin/run-skeleton-worker"]
