#!/bin/bash
#SBATCH -J Assemble_NF_KG                            # Job name
#SBATCH -N 2                                # Number of nodes
#SBATCH -n 32                               # Number of tasks
#SBATCH -o ./outputs/%x-%j.out
#SBATCH -e ./outputs/%x-%j.err
#SBATCH --mail-user=w.galbraith@northeastern.edu  # Email
#SBATCH --mail-type=ALL                     # Type of email notifications
#SBATCH --time=1-12:00:00 # 1 day 12 hours zero minutes
source $gl/dglink/.venv/bin/activate
python ./scripts/assemble_nf_kg.py
