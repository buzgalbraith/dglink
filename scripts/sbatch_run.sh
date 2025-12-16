#!/bin/bash
#SBATCH -J Assemble_NF_KG                            # Job name
#SBATCH -N 1                                # Number of nodes
#SBATCH -n 16                               # Number of tasks
#SBATCH -o ./outputs/output_%j.txt                    # Standard output file
#SBATCH -e ./outputs/error_%j.txt                     # Standard error file
#SBATCH --mail-user=$USER@northeastern.edu  # Email
#SBATCH --mail-type=ALL                     # Type of email notifications
#SBATCH --time=12:00:00
$gl/dglink/.venv/bin/python3 ./scripts/assemble_nf_kg.py
