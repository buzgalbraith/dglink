FROM --platform=linux/amd64 ubuntu:22.04

WORKDIR /sw

## install CLI packages
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    build-essential \
    cmake \
    git \
    zlib1g-dev \
    libbz2-dev \
    libssl-dev \
    libboost-all-dev \
    vim \
    && rm -rf /var/lib/apt/lists/*

## install SDSL
RUN git clone https://github.com/simongog/sdsl-lite.git
RUN cd sdsl-lite && ./install.sh /usr/local

## install mantis
RUN git clone https://github.com/splatlab/mantis.git
RUN mkdir /sw/mantis/build && \
    cd /sw/mantis/build && \
    cmake .. -DCMAKE_CXX_FLAGS="-include cstdint -include cstddef -include string" && \
    make install

## copy scripts
COPY scripts /sw/scripts

## python setup
COPY genomic_index_query_backend/requirements.txt /sw/requirements.txt
RUN pip install -r /sw/requirements.txt
COPY genomic_index_query_backend/main.py /sw/main.py

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]


