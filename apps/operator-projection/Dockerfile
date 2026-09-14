# operator-projection/v1 (§0): `operator-projection serve` on 0.0.0.0:8080 as uid/gid 65532.
# Nothing is written at runtime, so the pod runs with readOnlyRootFilesystem. The base is python slim, not
# distroless: the appservice init container uses this image's /bin/sh, cp and chmod to copy the credential
# Secret into the in-memory emptyDir at /run/vuoro/credentials.
#
# docker build --build-arg REGISTRY_COMMIT=$(git rev-parse HEAD) -t operator-projection:<version> apps/operator-projection

FROM python:3.12-slim-bookworm AS build
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim-bookworm
ARG REGISTRY_COMMIT=uncommitted
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /install /usr/local
COPY registry.yaml /app/registry.yaml
RUN printf '%s\n' "$REGISTRY_COMMIT" > /app/registry.commit
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["operator-projection"]
CMD ["serve"]
