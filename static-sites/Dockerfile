FROM public.ecr.aws/docker/library/python:3.11.4-bullseye as BUILDER
COPY /ark /ark
WORKDIR /ark
RUN pip install ark==7.1.0
RUN ark build

FROM public.ecr.aws/docker/library/caddy:2.7.4-alpine
COPY --from=builder /ark/out /usr/share/caddy/