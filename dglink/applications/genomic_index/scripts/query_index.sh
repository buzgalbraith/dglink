query_file=$1
mkdir -p /sw/query_results
mantis query \
	-p mantis_index \
	-1 \
	-j \
	-o /sw/query_results/$query_file.res \
	/sw/query_file
