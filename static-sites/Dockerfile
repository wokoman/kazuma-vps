FROM public.ecr.aws/docker/library/python:3.13-bullseye as BUILDER
COPY /ark /ark
WORKDIR /ark
RUN pip install ark==7.7.0
RUN ark build

FROM public.ecr.aws/docker/library/caddy:2.10-alpine
COPY --from=builder /ark/out /usr/share/caddy/
