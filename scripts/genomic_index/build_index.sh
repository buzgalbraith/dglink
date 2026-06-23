## build the genomic index in a Docker container ##
docker build \
	-t build-index \
	-f dglink/applications/genomic_index/Dockerfile.build-index \
	.
mkdir -p dglink/applications/genomic_index/mantis_index
docker run --rm -it \
        --env-file dglink/applications/genomic_index/.env \
        -v $(pwd)/dglink/applications/genomic_index/mantis_index:/sw/mantis_index \
        build-index /bin/bash -c \
        "
        python3 /sw/scripts/pull_fastq_files.py && \
        bash scripts/build_squeaker.sh && \
        bash /sw/scripts/build_mantis_index.sh
        "
