## remove to save space
rm -r fastq_files
## built mantis index
find squeakr_files/*.squeakr > squeakr_files/squeakr_files.lst
mantis build \
	-s 31 \
	-i squeakr_files/squeakr_files.lst \
	-o mantis_index

## build mst representation
mantis mst \
        -p mantis_index \
        -t 4 \
        -d

## clean up squeark files
rm -r squeakr_files
