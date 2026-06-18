#!/bin/bash
## run vars ##
export kmer_size=20
export slots=31
export threads=4 ## make sure this matches the sbatch config
export mb_size=100000 ## 100 mb size

## run method ##
mkdir -p squeakr_files 
## get squeakr files ##
echo "Creating squeakr files..."
for fastq_file in fastq_files/*.fastq*; do
	## determine the cut off ##
        size=$(du -k "$fastq_file" | awk -F '\t' '{print $1 }')
        if ((3* mb_size >= size)); then
                export cutoff=1;
        elif ((5 * mb_size >= size)); then
                export cutoff=3;
        elif ((10 * mb_size >= size)); then
                export cutoff=10;
        elif ((30 * mb_size >= size)); then
                export cutoff=20;
        else
                export cutoff=50;
        fi
	write_name=$(echo $fastq_file | sed 's/fastq_files/squeakr_files/' | sed 's/.fastq/.squeakr/' | sed 's/.gz//')
        echo $write_name $size $cutoff
        /bin/squeakr count \
		-e \
		-c $cutoff \
                --no-counts \
                -k $kmer_size \
                -s $slots \
                -t $threads \
                -o $write_name \
                $fastq_file
done
echo "squeakr done"

