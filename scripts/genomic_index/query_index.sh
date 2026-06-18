## query a pre-existing Mantis index with Docker
docker build \
	-t query-index \
	-f query-index/Dockerfile.query-index \
	.
query_file=${1:-"input_txns.fa"}
docker run --rm -it \
        --env-file dglink/applications/genomic_index/.env \
        -v $(pwd)/mantis_index:/sw/mantis_index \
        -v $(pwd)/$query_file:/sw/query_file \
        -v $(pwd)/query_results:/sw/query_results \
        query-index $query_file
