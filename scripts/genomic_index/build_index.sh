## build the genomic index in a Docker container ##
docker build \
	-t genomic-index \
	-f dglink/applications/genomic_index/Dockerfile.build-index \
	.
mkdir -p mantis_index
docker run --rm -it \
        --env-file dglink/applications/genomic_index/.env \
        -v $(pwd)/mantis_index:/sw/mantis_index \
        genomic-index /bin/bash -c \
        "
        python3 /sw/scripts/pull_fastq_files.py && \
        bash scripts/build_squeaker.sh && \
        bash /sw/scripts/build_mantis_index.sh
        "
