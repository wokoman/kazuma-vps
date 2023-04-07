FROM public.ecr.aws/docker/library/python:3.11.2-bullseye as BUILDER
COPY /ivy /ivy
WORKDIR /ivy
RUN pip install ivy==6.4.1
RUN ivy build

FROM public.ecr.aws/docker/library/caddy:2.6.4-alpine
COPY --from=builder /ivy/out /usr/share/caddy/