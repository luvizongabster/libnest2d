# Build stage
FROM ubuntu:24.04 AS builder

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    cmake \
    git \
    libboost-all-dev \
    libnlopt-dev \
    libnlopt-cxx-dev \
    libpolyclipping-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN git clone --depth 1 https://github.com/tamasmeszaros/libnest2d.git

WORKDIR /app/build
COPY CMakeLists.txt main.cpp ./
ENV NLopt_PATH=/usr
ENV CLIPPER_PATH=/usr
RUN cmake -B . \
    -D LIBNEST2D_SOURCE_DIR=/tmp/libnest2d \
    -D LIBNEST2D_BACKEND_CLIPPER=ON \
    -D LIBNEST2D_OPTIMIZER_NLOPT=ON \
    && cmake --build . --target nest_engine

# Runtime stage
FROM ubuntu:24.04 AS runtime

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    libnlopt0 \
    libnlopt-cxx0 \
    libpolyclipping22 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/build/nest_engine /app/nest_engine
WORKDIR /app
ENTRYPOINT ["/app/nest_engine"]
