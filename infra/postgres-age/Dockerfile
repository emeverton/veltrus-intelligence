FROM postgres:14

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    flex \
    bison \
    postgresql-server-dev-14 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch PG14/v1.5.0-rc0 \
    https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make \
    && make install \
    && rm -rf /tmp/age

RUN echo "shared_preload_libraries = 'age'" \
    >> /usr/share/postgresql/postgresql.conf.sample

COPY init.sql /docker-entrypoint-initdb.d/01_age_setup.sql
