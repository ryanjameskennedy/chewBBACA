#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Purpose
-------

This is the main script of the chewBBACA suite.

"""


import os
import sys
import shutil
import hashlib
import argparse

try:
    from __init__ import __version__
    from AlleleCall import allele_call
    from CreateSchema import create_schema
    from SchemaEvaluator import evaluate_schema
    from AlleleCallEvaluator import evaluate_calls
    from PrepExternalSchema import adapt_schema
    from UniprotFinder import annotate_schema
    from ExtractCgMLST import determine_cgmlst
    from utils import (join_profiles,
                       remove_genes,
                       # profiles_sqlitedb as ps,
                       process_datetime as pdt,
                       constants as ct,
                       parameters_validation as pv,
                       file_operations as fo)

    from utils.parameters_validation import ModifiedHelpFormatter

    from CHEWBBACA_NS import (download_schema, upload_schema,
                              synchronize_schema, stats_requests)
except ModuleNotFoundError:
    from CHEWBBACA import __version__
    from CHEWBBACA.AlleleCall import allele_call
    from CHEWBBACA.CreateSchema import create_schema
    from CHEWBBACA.SchemaEvaluator import evaluate_schema
    from CHEWBBACA.AlleleCallEvaluator import evaluate_calls
    from CHEWBBACA.PrepExternalSchema import adapt_schema
    from CHEWBBACA.UniprotFinder import annotate_schema
    from CHEWBBACA.ExtractCgMLST import determine_cgmlst
    from CHEWBBACA.utils import (join_profiles,
                                 remove_genes,
                                 # profiles_sqlitedb as ps,
                                 process_datetime as pdt,
                                 constants as ct,
                                 parameters_validation as pv,
                                 file_operations as fo)

    from CHEWBBACA.utils.parameters_validation import ModifiedHelpFormatter

    from CHEWBBACA.CHEWBBACA_NS import (download_schema, upload_schema,
                                        synchronize_schema, stats_requests)


version = __version__


@pdt.process_timer
def run_create_schema():
    """Run the CreateSchema module to create a schema seed."""

    def msg(name=None):
        # simple command to create schema from genomes
        simple_cmd = ('chewBBACA.py CreateSchema -i <input_files> '
                      '-o <output_directory> --ptf <ptf_path>')
        # command to create schema from genomes with non-default parameters
        params_cmd = ('chewBBACA.py CreateSchema -i <input_files> '
                      '-o <output_directory> --ptf <ptf_path>\n'
                      '\t\t\t    --cpu <cpu_cores> --bsr <blast_score_ratio> '
                      '--l <minimum_length>\n\t\t\t    --t <translation_table> '
                      '--st <size_threshold>')
        # command to create schema from FASTA with coding sequences
        cds_cmd = ('chewBBACA.py CreateSchema -i <input_files> '
                   '-o <output_directory> --ptf <ptf_path> '
                   '--cds')

        usage_msg = ('\nCreate schema from genome assemblies:\n  {0}\n'
                     '\nCreate schema with non-default parameters:\n  {1}\n'
                     '\nCreate schema from FASTA files with coding sequences:\n  {2}'.format(simple_cmd, params_cmd, cds_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='CreateSchema',
                                     description='Creates a schema seed based on a '
                                                 'set of FASTA files with genome '
                                                 'assemblies or coding sequences.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter,
                                     epilog='It is strongly advised to provide a training file to '
                                            'create a schema. Module documentation available at '
                                            'https://chewbbaca.readthedocs.io/en/latest/user/modules/CreateSchema.html')

    parser.add_argument('CreateSchema', nargs='+',
                        help='')

    parser.add_argument('-i', '--input-files', nargs='?', type=str,
                        required=True, dest='input_files',
                        help='Path to the directory that contains the input '
                             'FASTA files. Alternatively, a file with '
                             'a list of full paths to FASTA files, one per line.')

    parser.add_argument('-o', '--output-directory', type=str,
                        required=True, dest='output_directory',
                        help='Output directory where the process will store '
                             'intermediate files and create the schema\'s '
                             'directory.')

    parser.add_argument('--n', '--schema-name', type=str,
                        required=False, default='schema_seed',
                        dest='schema_name',
                        help='Name given to the folder that will store the '
                             'schema files.')

    parser.add_argument('--ptf', '--training-file', type=str,
                        required=False, dest='ptf_path',
                        help='Path to the Prodigal training file.')

    parser.add_argument('--bsr', '--blast-score-ratio', type=pv.bsr_type,
                        required=False, default=ct.DEFAULT_BSR,
                        dest='blast_score_ratio',
                        help='BLAST Score Ratio value. Sequences with '
                             'alignments with a BSR value equal to or '
                             'greater than this value will be considered '
                             'as sequences from the same gene.')

    parser.add_argument('--l', '--minimum-length', type=pv.minimum_sequence_length_type,
                        required=False, default=201, dest='minimum_length',
                        help='Minimum sequence length value. Coding sequences '
                             'shorter than this value are excluded.')

    parser.add_argument('--t', '--translation-table', type=pv.translation_table_type,
                        required=False, default=11, dest='translation_table',
                        help='Genetic code used to predict genes and'
                             ' to translate coding sequences.')

    parser.add_argument('--st', '--size-threshold', type=pv.size_threshold_type,
                        required=False, default=0.2, dest='size_threshold',
                        help='CDS size variation threshold. Added to the '
                             'schema\'s config file and used to identify '
                             'alleles with a length value that deviates from '
                             'the locus length mode during the allele calling '
                             'process.')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, default=1, dest='cpu_cores',
                        help='Number of CPU cores that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total'
                             'number of available CPU cores).')

    parser.add_argument('--b', '--blast-path', type=pv.check_blast,
                        required=False, default='', dest='blast_path',
                        help='Path to the directory that contains the '
                             'BLAST executables.')

    parser.add_argument('--pm', '--prodigal-mode', required=False,
                        choices=['single', 'meta'],
                        default='single', dest='prodigal_mode',
                        help='Prodigal running mode ("single" for '
                             'finished genomes, reasonable quality '
                             'draft genomes and big viruses. "meta" '
                             'for metagenomes, low quality draft '
                             'genomes, small viruses, and small '
                             'plasmids).')

    parser.add_argument('--cds', '--cds-input', required=False,
                        action='store_true', dest='cds_input',
                        help='If provided, chewBBACA skips the gene '
                             'prediction step and assumes the input FASTA '
                             'files contain coding sequences.')

    parser.add_argument('--no-cleanup', required=False, action='store_true',
                        dest='no_cleanup',
                        help='If provided, intermediate files generated '
                             'during process execution are not deleted at '
                             'the end.')

    args = parser.parse_args()
    del args.CreateSchema

    # Check if ptf exists
    if args.ptf_path is not None:
        ptf_exists = os.path.isfile(args.ptf_path)
        if ptf_exists is False:
            sys.exit('Invalid path for Prodigal training file.')

    # Create output directory
    created = fo.create_directory(args.output_directory)
    if created is False:
        sys.exit(ct.OUTPUT_DIRECTORY_EXISTS)

    genome_list = fo.join_paths(args.output_directory, [ct.GENOME_LIST])
    args.input_files = pv.check_input_type(args.input_files, genome_list)

    # Add clustering parameters
    args.word_size = ct.WORD_SIZE_DEFAULT
    args.window_size = ct.WINDOW_SIZE_DEFAULT
    args.clustering_sim = ct.CLUSTERING_SIMILARITY_DEFAULT
    args.representative_filter = ct.REPRESENTATIVE_FILTER_DEFAULT
    args.intra_filter = ct.INTRA_CLUSTER_DEFAULT

    # Run the CreateSchema process
    create_schema.main(**vars(args))

    schema_dir = os.path.join(args.output_directory, args.schema_name)
    # Copy Prodigal Training File (PTF) to schema directory
    ptf_hash = None
    if args.ptf_path is not None:
        shutil.copy(args.ptf_path, schema_dir)
        # Determine PTF checksum
        ptf_hash = fo.hash_file(args.ptf_path, hashlib.blake2b())

    # Write schema config file
    schema_config = pv.write_schema_config(args.blast_score_ratio, ptf_hash,
                                           args.translation_table, ct.MSL_MIN,
                                           version, args.size_threshold,
                                           args.word_size, args.window_size,
                                           args.clustering_sim, args.representative_filter,
                                           args.intra_filter, schema_dir)

    # Create the file with the list of genes/loci
    pv.write_gene_list(schema_dir)

    # Remove temporary file with paths to input genomes
    fo.remove_files([genome_list])


@pdt.process_timer
def run_allele_call():
    """Run the AlleleCall module to perform allele calling."""

    def msg(name=None):
        # simple command to perform AlleleCall with schema default parameters
        simple_cmd = ('chewBBACA.py AlleleCall -i <input_files> '
                      '-g <schema_directory> '
                      '-o <output_directory> ')
        # command to perform AlleleCall with non-default parameters
        params_cmd = ('chewBBACA.py AlleleCall -i <input_files> '
                      '-g <schema_directory> '
                      '-o <output_directory> '
                      '--cpu <cpu_cores> '
                      '\n\t\t\t  --bsr <blast_score_ratio> '
                      '--l <minimum_length>\n'
                      '\t\t\t  --t <translation_table> '
                      '--st <size_threshold>')
        # command to perform AlleleCall with Fasta files that contain CDS
        cds_cmd = ('chewBBACA.py AlleleCall -i <input_files> '
                                            '-g <schema_directory> '
                                            '-o <output_directory> '
                                            '--cds')

        usage_msg = ('\nPerform allele calling with schema default parameters:\n  {0}\n'
                     '\nPerform allele calling with non-default parameters:\n  {1}\n'
                     '\nPerform allele calling with FASTA files that contain CDSs:\n  {2}'.format(simple_cmd, params_cmd, cds_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='AlleleCall',
                                     description='Performs allele calling to determine the '
                                                 'allelic profiles of a set of samples in FASTA format. '
                                                 'The process identifies new alleles, assigns '
                                                 'an integer identifier to those alleles and '
                                                 'adds them to the schema.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter,
                                     epilog='It is strongly advised to perform allele calling '
                                            'with the default schema parameters to ensure '
                                            'more consistent results. Module documentation available at '
                                            'https://chewbbaca.readthedocs.io/en/latest/user/modules/AlleleCall.html')

    parser.add_argument('AlleleCall', nargs='+', help='')

    parser.add_argument('-i', '--input-files', nargs='?', type=str,
                        required=True, dest='input_files',
                        help='Path to the directory with the genome FASTA '
                             'files or to a file that contains a list of full paths to '
                             'the FASTA files, one per line.')

    parser.add_argument('-g', '--schema-directory', type=str,
                        required=True, dest='schema_directory',
                        help='Path to the schema directory. The schema '
                             'directory contains the loci FASTA files and '
                             'a folder named "short" that contains the '
                             'FASTA files with the loci representative '
                             'alleles.')

    parser.add_argument('-o', '--output-directory', type=str,
                        required=True, dest='output_directory',
                        help='Output directory where the allele calling '
                             'results will be stored (will create a '
                             'subdirectory named "results_<TIMESTAMP>" '
                             'if the path passed by the user already exists).')

    parser.add_argument('--ptf', '--training-file', type=str,
                        required=False, dest='ptf_path',
                        help='Path to the Prodigal training file. Default is '
                             'to get the training file from the schema\'s '
                             'directory')

    parser.add_argument('--gl', '--genes-list', type=str,
                        required=False, default=False, dest='genes_list',
                        help='Path to a file that contains the list of full paths '
                             'to the loci FASTA files or loci IDs, one per line, '
                             'the process should use to perform allele calling.')

    parser.add_argument('--bsr', '--blast-score-ratio', type=pv.bsr_type,
                        required=False, dest='blast_score_ratio',
                        help='BLAST Score Ratio value. Sequences with '
                             'alignments with a BSR value equal to or '
                             'greater than this value will be considered '
                             'as sequences from the same gene.')

    parser.add_argument('--l', '--minimum-length', type=pv.minimum_sequence_length_type,
                        required=False, dest='minimum_length',
                        help='Minimum sequence length accepted for a '
                             'coding sequence to be included in the schema.')

    parser.add_argument('--t', '--translation-table', type=pv.translation_table_type,
                        required=False, dest='translation_table',
                        help='Genetic code used to predict genes and'
                             ' to translate coding sequences. Must match '
                             'the genetic code used to create the training '
                             'file.')

    parser.add_argument('--st', '--size-threshold', type=pv.size_threshold_type,
                        required=False, dest='size_threshold',
                        help='CDS size variation threshold. At the default '
                             'value of 0.2, alleles with size that deviates '
                             '+-20 percent from the locus length mode will be '
                             'classified as ASM/ALM')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, default=1, dest='cpu_cores',
                        help='Number of CPU cores/threads that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total'
                             'number of available CPU cores/threads).')

    parser.add_argument('--b', '--blast-path', type=pv.check_blast,
                        required=False, default='', dest='blast_path',
                        help='Path to the directory that contains the '
                             'BLAST executables.')

    parser.add_argument('--pm', '--prodigal-mode', type=str,
                        required=False, choices=['single', 'meta'],
                        default='single', dest='prodigal_mode',
                        help='Prodigal running mode ("single" for '
                             'finished genomes, reasonable quality '
                             'draft genomes and big viruses. "meta" '
                             'for metagenomes, low quality draft '
                             'genomes, small viruses, and small '
                             'plasmids).')

    parser.add_argument('--cds', '--cds-input', action='store_true',
                        required=False, dest='cds_input',
                        help='Input files contain coding sequences (one '
                             'Fasta file per strain). chewBBACA skips the '
                             'gene prediction step with Prodigal if this '
                             'argument is provided.')

    parser.add_argument('--no-inferred', required=False,
                        action='store_true', dest='no_inferred',
                        help='If provided, the process will not add '
                             'the sequences of inferred alleles (INF) to the '
                             'schema. Allelic profiles will still include '
                             'the allele identifiers attributed to the '
                             'inferred alleles. Use this parameter if the '
                             'schema is being accessed by multiple '
                             'processes/users simultaneously.')

    parser.add_argument('--output-unclassified', required=False,
                        action='store_true', dest='output_unclassified',
                        help='Create Fasta file with unclassified '
                             'coding sequences.')

    parser.add_argument('--output-missing', required=False,
                        action='store_true', dest='output_missing',
                        help='Create Fasta file with coding sequences '
                             'classified as NIPH, NIPHEM, ASM, ALM, PLOT3, '
                             'PLOT5 and LOTSC.')

    parser.add_argument('--output-novel', required=False,
                        action='store_true', dest='output_novel',
                        help='Create Fasta file with the novel alleles '
                             'inferred during the allele calling. The '
                             'sequence headers include the locus and allele '
                             'identifiers attributed by chewBBACA based '
                             'on the allele calling results')

    parser.add_argument('--no-cleanup', required=False,
                        action='store_true', dest='no_cleanup',
                        help='If provided, intermediate files generated '
                             'during process execution are not removed at '
                             'the end.')

    parser.add_argument('--hash-profiles', type=str, required=False,
                        dest='hash_profiles',
                        help='Create TSV file with hashed allelic profiles. '
                             'Profiles can be hashed with any of the hash '
                             'algorithms implemented in the hashlib and zlib '
                             'libraries.')

    # parser.add_argument('--db', '--store-profiles', required=False,
    #                     action='store_true', dest='store_profiles',
    #                     help='If the profiles in the output matrix '
    #                          'should be stored in the local SQLite '
    #                          'database.')

    parser.add_argument('--force-continue', required=False,
                        action='store_true', dest='force_continue',
                        help='If provided, chewBBACA will add config files '
                             'with default parameter values to schemas that '
                             ' are missing those files and will also proceed '
                             'if any of the argument values does not match '
                             'the value in the config files. Otherwise, it '
                             'will prompt users for the parameter values to '
                             'add to the config files and for permission to '
                             'proceed if the argument values differ from the '
                             'ones in the config files.')

    parser.add_argument('--mode', type=int, required=False,
                        choices=[1, 2, 3, 4], default=4,
                        help='Execution mode (1: only exact matches at DNA '
                             'level; 2: exact matches at DNA and Protein '
                             'level; 3: exact matches and minimizer-based '
                             'clustering to find similar alleles based on '
                             'BSR+0.1; 4: runs the full process to find '
                             'exact matches and similar matches based on '
                             'BSR value, including the determination of new '
                             'representative alleles to add to the schema).')

    args = parser.parse_args()

    # Check if input schema path exists
    if not os.path.exists(args.schema_directory):
        sys.exit(ct.SCHEMA_PATH_MISSING)

    # Verify schema files
    schema_files = os.listdir(args.schema_directory)
    # Exit if there is no 'short' directory or if there are no FASTA files
    if 'short' not in schema_files or len(fo.filter_by_extension(schema_files, ['.fasta'])[0]) == 0:
        sys.exit(ct.SCHEMA_INVALID_PATH)

    config_file = os.path.join(args.schema_directory, '.schema_config')
    # Legacy schemas do not have config file
    # Tell users to adapt with PrepExternalSchema module
    if os.path.isfile(config_file) is False:
        sys.exit(ct.ADAPT_LEGACY_SCHEMA)
    else:
        schema_params = fo.pickle_loader(config_file)
        # Chek if user provided different values
        run_params = pv.solve_conflicting_arguments(schema_params, args.ptf_path,
                                                    args.blast_score_ratio, args.translation_table,
                                                    args.minimum_length, args.size_threshold,
                                                    args.force_continue, config_file, args.schema_directory)
        args.ptf_path = run_params['ptf_path']
        args.blast_score_ratio = run_params['bsr']
        args.translation_table = run_params['translation_table']
        args.minimum_length = run_params['minimum_locus_length']
        args.size_threshold = run_params['size_threshold']

    # Create output directory
    created = fo.create_directory(args.output_directory)
    # Output directory exists
    # Create a subdirectory to store intermediate files and results
    if created is False:
        current_time = pdt.get_datetime()
        current_time_str = pdt.datetime_str(current_time,
                                            date_format='%Y%m%dT%H%M%S')
        results_dir = fo.join_paths(args.output_directory,
                                    ['results_{0}'.format(current_time_str)])
        created = fo.create_directory(results_dir)
        args.output_directory = results_dir
        print('Output directory exists. Will store results in '
              '{0}.'.format(results_dir))

    loci_list = fo.join_paths(args.output_directory, [ct.LOCI_LIST])
    # User provided a list of genes to call
    if args.genes_list is not False:
        loci_list = pv.validate_loci_list(args.genes_list, loci_list,
                                          args.schema_directory)
    # Working with the whole schema
    else:
        loci_list = pv.check_input_type(args.schema_directory, loci_list)

    genome_list = fo.join_paths(args.output_directory, [ct.GENOME_LIST])
    genome_list = pv.check_input_type(args.input_files, genome_list)

    # Determine if schema was downloaded from Chewie-NS
    ns_config = fo.join_paths(args.schema_directory, ['.ns_config'])
    args.ns = os.path.isfile(ns_config)

    # Add clustering arguments
    args.word_size = ct.WORD_SIZE_DEFAULT
    args.window_size = ct.WINDOW_SIZE_DEFAULT
    args.clustering_sim = ct.CLUSTERING_SIMILARITY_DEFAULT

    # Single dictionary with most arguments
    config = {'Minimum sequence length': args.minimum_length,
              'Size threshold': args.size_threshold,
              'Translation table': args.translation_table,
              'BLAST Score Ratio': args.blast_score_ratio,
              'Word size': args.word_size,
              'Window size': args.window_size,
              'Clustering similarity': args.clustering_sim,
              'Prodigal training file': args.ptf_path,
              'CPU cores': args.cpu_cores,
              'BLAST path': args.blast_path,
              'CDS input': args.cds_input,
              'Prodigal mode': args.prodigal_mode,
              'Mode': args.mode}

    allele_call.main(genome_list, loci_list, args.schema_directory,
                     args.output_directory, args.no_inferred,
                     args.output_unclassified, args.output_missing,
                     args.output_novel, args.no_cleanup, args.hash_profiles,
                     args.ns, config)

    # if args.store_profiles is True:
    #     updated = ps.store_allelecall_results(args.output_directory, args.schema_directory)

    # Remove temporary files with paths to input genomes and schema files
    fo.remove_files([loci_list])
    fo.remove_files([genome_list])


@pdt.process_timer
def run_evaluate_schema():
    """Run the SchemaEvaluator module to evaluate a typing schema."""

    def msg(name=None):
        # simple command to evaluate schema or set of loci
        simple_cmd = ('chewBBACA.py SchemaEvaluator -g <schema_directory> '
                      '-o <output_directory> --cpu <cpu_cores> --loci-reports')

        usage_msg = (
            '\nEvaluate schema with default parameters:\n  {0}\n'.format(simple_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='SchemaEvaluator',
                                     description='Evaluate the number of alelles and allele size '
                                                 'variation for the loci in a schema or for a set '
                                                 'of selected loci. Provide information about '
                                                 'problematic alleles per locus and individual pages '
                                                 'for each locus with a plot with allele size, a Neighbor '
                                                 'Joining tree based on a multiple sequence alignment (MSA) '
                                                 'and a visualization of the MSA.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('SchemaEvaluator', nargs='+',
                        help='Evaluates a set of loci.')

    parser.add_argument('-g', '--schema-directory', type=str, required=True,
                        dest='schema_directory',
                        help='Path to the schema\'s directory.')

    parser.add_argument('-o', '--output-directory', type=str, required=True,
                        dest='output_directory',
                        help='Path to the output directory where the report '
                             'HTML files will be generated.')

    parser.add_argument('--gl', '--genes-list', type=str,
                        required=False, default=False, dest='genes_list',
                        help='Path to a file with the list of loci '
                             'in the schema that the process should '
                             'analyse (one per line, full path or loci IDs).')

    parser.add_argument('-a', '--annotations', type=str, required=False,
                        dest='annotations',
                        help='Path to the TSV file created by the '
                             'UniprotFinder module.')

    parser.add_argument('--ta', '--translation-table',
                        type=pv.translation_table_type, required=False,
                        dest='translation_table',
                        help='Genetic code used to translate coding '
                             'sequences.')

    parser.add_argument('--st', '--size-threshold',
                        type=pv.size_threshold_type,
                        required=False, dest='size_threshold',
                        help='Allele size variation threshold. If an allele '
                             'has a size within the interval of the locus '
                             'mode -/+ the threshold.')

    parser.add_argument('--ml', '--minimum-length',
                        type=pv.minimum_sequence_length_type,
                        required=False, dest='minimum_length',
                        help='Minimum sequence length accepted for a '
                             'coding sequence to be included in the schema.')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, default=1, dest='cpu_cores',
                        help='Number of CPU cores/threads that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total'
                             'number of available CPU cores/threads).')

    parser.add_argument('--loci-reports', required=False,
                        action='store_true', dest='loci_reports',
                        help='If the process should create an individual '
                             'report for each locus.')

    parser.add_argument('--light', action='store_true', required=False,
                        dest='light',
                        help='If determining loci reports, skips MSA '
                             'computation with MAFFT and does not add '
                             'the Phylogenetic Tree and MSA components.')

    parser.add_argument('--add-sequences', required=False,
                        action='store_true', dest='add_sequences',
                        help='Adds Code Editor components with the DNA and Protein '
                             'sequences to loci reports. The Code Editor '
                             'is in readonly mode (allows to search for '
                             'and copy text).')

    args = parser.parse_args()
    del args.SchemaEvaluator

    # Check if input schema path exists
    if not os.path.exists(args.schema_directory):
        sys.exit(ct.SCHEMA_PATH_MISSING)

    # Create output directory
    created = fo.create_directory(args.output_directory)
    if created is False:
        sys.exit(ct.OUTPUT_DIRECTORY_EXISTS)

    loci_list = fo.join_paths(args.output_directory, [ct.LOCI_LIST])
    # User provided a loci subset to analyse
    if args.genes_list is not False:
        loci_list = pv.validate_loci_list(args.genes_list, loci_list,
                                          args.schema_directory)
    # Working with the whole schema
    else:
        loci_list = pv.check_input_type(args.schema_directory, loci_list)

    args.genes_list = loci_list

    evaluate_schema.main(**vars(args))

    # Delete file with list of loci that were evaluated
    fo.remove_files([loci_list])


@pdt.process_timer
def run_evaluate_calls():
    """Run the AlleleCallEvaluator module to evaluate allele calling results."""

    def msg(name=None):
        # simple command to analyse allele calling results
        simple_cmd = ('chewBBACA.py AlleleCallEvaluator -i <input_files> '
                      '-g <schema_directory> -o <output_directory>')

        usage_msg = (
            '\nAnalyse allele calling results with default parameters:\n  {0}\n'.format(simple_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='AlleleCallEvaluator',
                                     description='',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('AlleleCallEvaluator', nargs='+',
                        help='Evaluates allele calling results.')

    parser.add_argument('-i', '--input-files', type=str, required=True,
                        dest='input_files',
                        help='Path to the directory that contains the allele '
                        'calling results.')

    parser.add_argument('-g', '--schema-directory', type=str, required=True,
                        dest='schema_directory',
                        help='Path to the schema directory.')

    parser.add_argument('-o', '--output-directory', type=str, required=True,
                        dest='output_directory',
                        help='Path to the output directory where the report '
                             'HTML files will be generated.')

    parser.add_argument('-a', '--annotations', type=str, required=False,
                        dest='annotations',
                        help='Path to the TSV file created by the '
                             'UniprotFinder module.')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, default=1, dest='cpu_cores',
                        help='Number of CPU cores/threads that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total'
                             'number of available CPU cores/threads).')

    parser.add_argument('--light', action='store_true', required=False,
                        dest='light',
                        help='Do not compute the presence-absence matrix, '
                             'the distance matrix and the Neighbor-Joining tree.')

    parser.add_argument('--no-pa', action='store_true', required=False,
                        dest='no_pa',
                        help='Do not compute the presence-absence matrix.')

    parser.add_argument('--no-dm', action='store_true', required=False,
                        dest='no_dm',
                        help='Do not compute the distance matrix.')

    parser.add_argument('--no-tree', action='store_true', required=False,
                        dest='no_tree',
                        help='Do not compute the Neighbor-Joining tree.')

    parser.add_argument('--cg-alignment', action='store_true', required=False,
                        dest='cg_alignment',
                        help='Compute the MSA of the core genome loci, even '
                             'if `--no-tree` is provided.')

    args = parser.parse_args()
    del args.AlleleCallEvaluator

    # Check if path to input files exists
    if not os.path.exists(args.input_files):
        sys.exit('Path to input files does not exist. Please provide a valid path.')

    # Create output directory
    created = fo.create_directory(args.output_directory)
    if created is False:
        sys.exit(ct.OUTPUT_DIRECTORY_EXISTS)

    evaluate_calls.main(**vars(args))


@pdt.process_timer
def run_determine_cgmlst():
    """Run the ExtractCgMLST module to determine the core-genome."""

    def msg(name=None):
        # simple command to determine loci that constitute cgMLST
        simple_cmd = ('  chewBBACA.py ExtractCgMLST -i <input_file> '
                      '-o <output_directory> ')

        # command to determine cgMLST with custom threshold
        threshold_cmd = ('  chewBBACA.py ExtractCgMLST -i <input_file> '
                         '-o <output_directory> '
                         '\n\t\t\t     --t <threshold>')

        # command to remove specific genes and genomes from the analysis
        remove_cmd = ('  chewBBACA.py ExtractCgMLST -i <input_file> '
                      '-o <output_directory> '
                      '\n\t\t\t     --r <genes2remove> '
                      '--g <genomes2remove>')

        usage_msg = ('\nDetermine cgMLST:\n{0}\n'
                     '\nDetermine cgMLST based on non-default threshold:\n{1}\n'
                     '\nRemove genes and genomes from matrix:\n{2}\n'
                     ''.format(simple_cmd, threshold_cmd, remove_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='ExtractCgMLST',
                                     description='Determines the set of '
                                                 'loci that constitute the '
                                                 'core genome based on loci presence thresholds.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('ExtractCgMLST', nargs='+',
                        help='')

    parser.add_argument('-i', '--input-file', type=str,
                        required=True, dest='input_file',
                        help='Path to input file containing a matrix with '
                             'allelic profiles.')

    parser.add_argument('-o', '--output-directory', type=str,
                        required=True, dest='output_directory',
                        help='Path to the directory where the process '
                             'will store output files.')

    parser.add_argument('--t', '--threshold', nargs='+', type=float,
                        required=False, default=ct.CGMLST_THRESHOLDS,
                        dest='threshold',
                        help='Genes that constitute the core genome '
                             'must be in a proportion of genomes that is '
                             'at least equal to this value. Users can '
                             'provide multiple values.')

    parser.add_argument('--s', '--step', type=int,
                        required=False, default=1,
                        dest='step',
                        help='Number of genomes added to the cgMLST '
                             'computation at each step.')

    parser.add_argument('--r', '--genes2remove', type=str,
                        required=False, default=False, dest='genes2remove',
                        help='Path to file with a list of genes/columns to '
                             'remove from the matrix (one gene identifier '
                             'per line).')

    parser.add_argument('--g', '--genomes2remove', type=str,
                        required=False, default=False, dest='genomes2remove',
                        help='Path to file with a list of genomes/rows to '
                             'remove from the matrix (one genome identifier '
                             'per line).')

    args = parser.parse_args()
    del args.ExtractCgMLST

    determine_cgmlst.main(**vars(args))


@pdt.process_timer
def run_remove_genes():
    """Run the RemoveGenes module to remove loci from allele calling results."""

    def msg(name=None):

        # simple command to remove a set of genes/columns from a matrix
        simple_cmd = ('  chewBBACA.py RemoveGenes -i <input_file> '
                      '-g <genes_list> '
                      '-o <output_file>')

        usage_msg = (
            '\nRemove a set of genes from a matrix with allelic profiles:\n{0}\n'.format(simple_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='RemoveGenes',
                                     description='Remove loci from a matrix with allelic profiles.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('RemoveGenes', nargs='+',
                        help='Remove loci from a matrix with allelic '
                             'profiles.')

    parser.add_argument('-i', '--input-file', type=str,
                        required=True, dest='input_file',
                        help='TSV file that contains a matrix with allelic '
                             'profiles determined by the AlleleCall process.')

    parser.add_argument('-g', '--genes-list', type=str,
                        required=True, dest='genes_list',
                        help='File with the list of genes to remove, one '
                             'identifier per line.')

    parser.add_argument('-o', '--output-file', type=str,
                        required=True, dest='output_file',
                        help='Path to the output file.')

    parser.add_argument('--inverse', action='store_true',
                        default=False, dest='inverse',
                        help='List of genes that is provided is the list of '
                             'genes to keep and all other genes should be '
                             'removed.')

    args = parser.parse_args()
    del args.RemoveGenes

    remove_genes.main(**vars(args))


@pdt.process_timer
def run_join_profiles():
    """Run the JoinProfiles module to join allele calling results."""

    def msg(name=None):

        # simple command to adapt external schema with default arguments values
        simple_cmd = ('  chewBBACA.py JoinProfiles -p <profiles1> <profiles2> '
                      '-o <output_file> ')

        usage_msg = ('\nJoin allele calling results from two runs:\n\n{0}\n'.format(simple_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='JoinProfiles',
                                     description='Joins allele calling results from '
                                                 'multiple runs.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('JoinProfiles', nargs='+',
                        help='')

    parser.add_argument('-p', '--profiles', nargs='+', type=str,
                        required=True, dest='profiles',
                        help='Path to the files containing the results from '
                             'the AlleleCall process (the AlleleCall process '
                             'saves the allelic profiles in the '
                             '"results_alleles.tsv" file).')

    parser.add_argument('-o', '--output-file', type=str,
                        required=True, dest='output_file',
                        help='Path to the output file.')

    parser.add_argument('--common', action='store_true',
                        required=False, dest='common',
                        help='Create file with profiles for the set of '
                             'common loci.')

    args = parser.parse_args()
    del args.JoinProfiles

    join_profiles.main(**vars(args))


@pdt.process_timer
def run_adapt_schema():
    """Run the PrepExternalSchema module to adapt a typing schema."""

    def msg(name=None):

        # Simple command to adapt external schema with default argument values
        simple_cmd = ('  chewBBACA.py PrepExternalSchema -g <schema_directory> '
                      '-o <output_directory> '
                      '--ptf <ptf_path> ')

        # Command to adapt external schema with non-default argument values
        params_cmd = ('  chewBBACA.py PrepExternalSchema -g <schema_directory> '
                      '-o <output_directory> '
                      '--ptf <ptf_path>\n'
                      '\t\t\t\t  --cpu <cpu_cores> '
                      '--bsr <blast_score_ratio> '
                      '--l <minimum_length>\n'
                      '\t\t\t\t  --t <translation_table> '
                      '--st <size_threshold>')

        usage_msg = ('\nAdapt external schema (one FASTA file per schema gene):\n\n{0}\n'
                     '\nAdapt external schema with non-default parameters:\n\n{1}\n'.format(simple_cmd, params_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='PrepExternalSchema',
                                     description='Enables the '
                                                 'adaptation of external '
                                                 'schemas so that the loci '
                                                 'and alleles present in '
                                                 'those schemas can be used '
                                                 'with chewBBACA. During '
                                                 'the process, alleles that '
                                                 'do not correspond to a '
                                                 'complete CDS or that cannot '
                                                 'be translated are discarded '
                                                 'from the final schema. One '
                                                 'or more alleles of each '
                                                 'gene/locus will be chosen '
                                                 'as representatives and '
                                                 'included in the "short" '
                                                 'directory.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('PrepExternalSchema', nargs='+',
                        help='')

    parser.add_argument('-g', '--schema-directory', type=str,
                        required=True, dest='schema_directory',
                        help='Path to the directory that contains the schema '
                             'FASTA files to adapt, one FASTA file per gene/locus.')

    parser.add_argument('-o', '--output-directory', type=str,
                        required=True, dest='output_directory',
                        help='The directory where the output files will be '
                             'saved (will create the directory if it does not '
                             'exist).')

    parser.add_argument('--gl', '--genes-list', type=str,
                        required=False, default=False, dest='genes_list',
                        help='Path to a file that contains the list of full paths '
                             'to the loci FASTA files or the loci IDs, one per line, '
                             'the process should adapt.')

    parser.add_argument('--ptf', '--training-file', type=str,
                        required=False, dest='ptf_path',
                        help='Path to the Prodigal training file that '
                             'will be included in the adapted schema.')

    parser.add_argument('--bsr', '--blast-score-ratio', type=pv.bsr_type,
                        required=False, default=ct.DEFAULT_BSR,
                        dest='blast_score_ratio',
                        help='The BLAST Score Ratio value that will be '
                             'used to adapt the external schema.')

    parser.add_argument('--l', '--minimum-length',
                        type=pv.minimum_sequence_length_type, required=False,
                        default=ct.MSL_MIN, dest='minimum_length',
                        help='Minimum sequence length value stored in the '
                             'schema config file. The schema adaptation '
                             'process will only discard sequences smaller '
                             'than the minimum length value if the '
                             '--size-filter parameter is provided.')

    parser.add_argument('--t', '--translation-table',
                        type=pv.translation_table_type, required=False,
                        default=11, dest='translation_table',
                        help='Genetic code to use for CDS translation.')

    parser.add_argument('--st', '--size-threshold', type=pv.size_threshold_type,
                        required=False, default=ct.SIZE_THRESHOLD_DEFAULT,
                        dest='size_threshold',
                        help='Allele size variation threshold value stored in '
                             'the schema config file. The schema adaptation '
                             'process will only discard sequences below or '
                             'above the size theshold value if the '
                             '--size-filter parameter is provided (at the '
                             'default value of 0.2, alleles with size '
                             'variation +-20 percent when compared to the '
                             'selected representatives will not be included '
                             'in the final schema.')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, default=1, dest='cpu_cores',
                        help='Number of CPU cores/threads that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total '
                             'number of available CPU cores/threads).')

    parser.add_argument('--b', '--blast-path', type=pv.check_blast,
                        required=False, default='', dest='blast_path',
                        help='Path to the directory that contains the '
                             'BLAST executables.')

    parser.add_argument('--size-filter', action='store_true',
                        required=False, dest='size_filter',
                        help='Apply the minimum length and size threshold'
                             ' values to filter out alleles during schema '
                             'adaptation.')

    args = parser.parse_args()
    del args.PrepExternalSchema

    # Check if ptf exists
    if args.ptf_path is not None:
        ptf_exists = os.path.isfile(args.ptf_path)
        if ptf_exists is False:
            sys.exit('Invalid path for Prodigal training file.')

    # Define output paths
    schema_path = os.path.abspath(args.output_directory)
    schema_short_path = fo.join_paths(schema_path, ['short'])
    output_dirs = [schema_path, schema_short_path]

    # Create output directories
    schema_path_exists = fo.create_directory(schema_path)
    if schema_path_exists is False:
        sys.exit(ct.OUTPUT_DIRECTORY_EXISTS)
    fo.create_directory(schema_short_path)

    # User provided a list of genes to call
    loci_list = fo.join_paths(schema_path, [ct.LOCI_LIST])
    if args.genes_list is not False:
        loci_list = pv.validate_loci_list(args.genes_list, loci_list,
                                          args.schema_directory)
    # Working with the whole schema
    else:
        loci_list = pv.check_input_type(args.schema_directory, loci_list)

    print(f'Number of cores: {args.cpu_cores}')
    print(f'BLAST Score Ratio: {args.blast_score_ratio}')
    print(f'Translation table: {args.translation_table}')

    # Only apply minimum length and size threshold during schema
    # adaptation if --size-filter parameter is True
    if args.size_filter:
        adaptation_st = args.size_threshold
        adaptation_ml = args.minimum_length
    else:
        adaptation_st = None
        adaptation_ml = 0

    print(f'Using a minimum length value of {adaptation_ml} for schema '
          f'adaptation and {args.minimum_length} to store in the schema '
          'config file.')
    print(f'Using a size threshold value of {adaptation_st} for schema '
          f'adaptation and {args.size_threshold} to store in the schema '
          'config file.')

    adapt_schema.main(loci_list, output_dirs,
                      args.cpu_cores, args.blast_score_ratio,
                      adaptation_ml, args.translation_table,
                      adaptation_st, args.blast_path)

    # Copy training file to schema directory
    ptf_hash = None
    if args.ptf_path is not None:
        shutil.copy(args.ptf_path, schema_path)
        # Determine PTF checksum
        ptf_hash = fo.hash_file(args.ptf_path, hashlib.blake2b())
        print('Copied Prodigal training file to schema directory.')

    # Write schema config file
    schema_config = pv.write_schema_config(args.blast_score_ratio, ptf_hash,
                                           args.translation_table, args.minimum_length,
                                           version, args.size_threshold, ct.WORD_SIZE_DEFAULT,
                                           ct.WINDOW_SIZE_DEFAULT, ct.CLUSTERING_SIMILARITY_DEFAULT,
                                           ct.REPRESENTATIVE_FILTER_DEFAULT, ct.INTRA_CLUSTER_DEFAULT,
                                           schema_path)

    # Create hidden file with list of loci
    genes_list_file = pv.write_gene_list(schema_path)

    # Delete file with list of loci to adapt
    os.remove(loci_list)


@pdt.process_timer
def run_annotate_schema():
    """Run the UniprotFinder module to annotate loci in a schema."""

    def msg(name=None):

        # Simple command to find annotations by querying Uniprot's SPARQL endpoint
        # and aligning against reference proteomes
        simple_cmd = ('  chewBBACA.py UniprotFinder -g <schema_directory> '
                      '-o <output_directory> -t <protein_table>\n'
                      '\t\t\t     --taxa "Streptococcus agalactiae" '
                      '--cpu <cpu_cores>')

        # Command to align against the reference proteomes of several species
        multiple_cmd = ('  chewBBACA.py UniprotFinder -g <schema_directory> '
                        '-t <protein_table> -o <output_directory>\n'
                        '\t\t\t     --taxa "Streptococcus agalactiae" "Streptococcus pyogenes" '
                        '--cpu <cpu_cores>')

        # Command to align against the reference proteomes at genus level
        genus_cmd = ('  chewBBACA.py UniprotFinder -g <schema_directory> '
                      '-t <protein_table> -o <output_directory>\n'
                      '\t\t\t     --taxa "Streptococcus" '
                      '--cpu <cpu_cores>')

        usage_msg = ('\nFind annotations for loci in a schema:\n\n{0}\n'
                     '\nAlign against reference proteomes of several species:\n\n{1}\n'
                     '\nAlign against reference proteomes of a genus:\n\n{2}\n'.format(simple_cmd,
                                                                                       multiple_cmd,
                                                                                       genus_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='UniprotFinder',
                                     description='Determines loci annotations based '
                                                 'on exact matches found in UniProt\'s '
                                                 'database and based on alignment against '
                                                 'reference proteomes for a set of taxa.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('UniprotFinder', nargs='+',
                        help='')

    parser.add_argument('-g', '--schema-directory', type=str,
                        required=True, dest='schema_directory',
                        help='Path to the schema directory. The schema '
                             'directory contains the loci FASTA files and '
                             'a folder named "short" that contains the '
                             'FASTA files with the loci representative '
                             'alleles.')

    parser.add_argument('-o', '--output-directory', type=str,
                        required=True, dest='output_directory',
                        help='Output directory where the process will '
                             'store intermediate files and save the final '
                             'TSV file with the annotations.')

    parser.add_argument('--gl', '--genes-list', type=str,
                        required=False, default=False, dest='genes_list',
                        help='Path to a file that contains the list of full paths '
                             'to the loci FASTA files or the loci IDs, one per line, '
                             'the process should find annotations for.')

    parser.add_argument('-t', '--protein-table', type=str,
                        required=False, dest='protein_table',
                        help='Path to the "cds_coordinates.tsv" file created by '
                             'the CreateSchema process.')

    parser.add_argument('--bsr', type=float, required=False,
                        dest='blast_score_ratio',
                        default=0.6,
                        help='BLAST Score Ratio value. This value is only '
                             'used when a taxon/taxa is provided and local '
                             'sequences are aligned against reference '
                             'proteomes.')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, default=1, dest='cpu_cores',
                        help='Number of CPU cores/threads that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total'
                             'number of available CPU cores/threads). '
                             'This value is only used if local sequences '
                             'are aligned against reference proteomes with '
                             'BLASTp.')

    parser.add_argument('--taxa', nargs='+', type=str,
                        required=False, dest='taxa',
                        help='List of scientific names for a set of taxa. The '
                             'process will search for and download reference '
                             'proteomes with terms that match any of the '
                             'provided taxa.')

    parser.add_argument('--pm', type=int, required=False,
                        default=1, dest='proteome_matches',
                        help='Maximum number of proteome matches to report.')

    parser.add_argument('--no-sparql', action='store_true',
                        required=False, dest='no_sparql',
                        help='Do not search for annotations through '
                             'UniProt SPARQL endpoint.')

    parser.add_argument('--no-cleanup', action='store_true',
                        required=False, dest='no_cleanup',
                        help='If provided, intermediate files generated '
                             'during process execution are not removed '
                             'at the end.')

    parser.add_argument('--b', '--blast-path', type=pv.check_blast,
                        required=False, default='', dest='blast_path',
                        help='Path to the directory that contains the '
                             'BLAST executables.')

    args = parser.parse_args()
    del args.UniprotFinder

    annotate_schema.main(**vars(args))


@pdt.process_timer
def run_download_schema():
    """Run the DownloadSchema module to download a schema from Chewie-NS."""

    def msg(name=None):
        # simple command to download a schema from the NS
        simple_cmd = ('  chewBBACA.py DownloadSchema -sp <species_id> '
                      '-sc <schema_id> '
                      '-o <download_folder> ')

        # command to download a schema from the NS with non-default arguments values
        params_cmd = ('  chewBBACA.py DownloadSchema -sp <species_id> '
                      '-sc <schema_id> '
                      '-o <download_folder>\n'
                      '\t\t\t      --cpu <cpu_cores> '
                      '--ns <nomenclature_server_url> ')

        usage_msg = ('\nDownload schema:\n{0}\n'
                     '\nDownload schema with non-default parameters:\n{1}\n'.format(simple_cmd, params_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='DownloadSchema',
                                     description='This program downloads '
                                                 'a schema from chewie-NS.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('DownloadSchema', nargs='+',
                        help='')

    parser.add_argument('-sp', '--species-id', type=str,
                        required=True, dest='species_id',
                        help='The integer identifier or name of the species '
                             'that the schema is associated to in Chewie-NS.')

    parser.add_argument('-sc', '--schema-id', type=str,
                        required=True, dest='schema_id',
                        help='The URI, integer identifier or name of '
                             'the schema to download from Chewie-NS.')

    parser.add_argument('-o', '--download-folder', type=str,
                        required=True, dest='download_folder',
                        help='Output folder to which the schema will '
                             'be saved.')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, default=1, dest='cpu_cores',
                        help='Number of CPU cores/threads that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total'
                             'number of available CPU cores/threads). '
                             'This value is only used if local sequences '
                             'are aligned against reference proteomes with '
                             'BLASTp. This value is only used if it is '
                             'necessary to construct the schema locally.')

    parser.add_argument('--ns', '--nomenclature-server', type=pv.validate_ns_url,
                        required=False, default='main', dest='nomenclature_server',
                        help='The base URL for the Chewie-NS instance. '
                             'The default value, "main", will establish a '
                             'connection to "https://chewbbaca.online/", '
                             '"tutorial" to "https://tutorial.chewbbaca.online/" '
                             'and "local" to "http://127.0.0.1:5000/NS/api/" (localhost). '
                             'Users may also provide the IP address to other '
                             'Chewie-NS instances.')

    parser.add_argument('--b', '--blast-path', type=pv.check_blast,
                        required=False, default='', dest='blast_path',
                        help='Path to the directory that contains the '
                             'BLAST executables.')

    parser.add_argument('--d', '--date', type=str,
                        required=False, default=None, dest='date',
                        help='Download schema with state from specified date. '
                             'Must be in the format "Y-m-dTH:M:S".')

    parser.add_argument('--latest', action='store_true',
                        required=False, dest='latest',
                        help='If the compressed version that is available is '
                             'not the latest, downloads all loci FASTA files '
                             'and constructs schema locally.')

    args = parser.parse_args()
    del args.DownloadSchema

    download_schema.main(**vars(args))


@pdt.process_timer
def run_upload_schema():
    """Run the LoadSchema module to upload a schema to Chewie-NS."""

    def msg(name=None):
        # simple command to load a schema to the NS
        simple_cmd = ('  chewBBACA.py LoadSchema -i <schema_directory> '
                      '-sp <species_id> '
                      '-sn <schema_name>\n'
                      '\t\t\t  -lp <loci_prefix> ')

        # command to load a schema to the NS with non-default arguments values
        params_cmd = ('  chewBBACA.py LoadSchema -i <schema_directory> '
                      '-sp <species_id> '
                      '-sn <schema_name>\n'
                      '\t\t\t  -lp <loci_prefix> '
                      '--ns <nomenclature_server_url>')

        # command to continue schema upload that was interrupted or aborted
        continue_cmd = ('  chewBBACA.py LoadSchema -i <schema_directory> '
                        '-sp <species_id> '
                        '-sn <schema_name>\n'
                        '\t\t\t  --continue_up')

        usage_msg = ('\nLoad schema:\n{0}\n'
                     '\nLoad schema with non-default parameters:\n{1}\n'
                     '\nContinue schema upload that was interrupted or aborted:\n{2}\n'.format(simple_cmd, params_cmd, continue_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='LoadSchema',
                                     description='This program uploads '
                                                 'a schema to the NS.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('LoadSchema', nargs='+',
                        help='')

    parser.add_argument('-i', '--schema-directory', type=str,
                        required=True, dest='schema_directory',
                        help='Path to the directory of the schema to upload.')

    parser.add_argument('-sp', '--species-id', type=str,
                        required=True, dest='species_id',
                        help='The integer identifier or name of the species '
                             'that the schema will be associated to in '
                             'Chewie-NS.')

    parser.add_argument('-sn', '--schema-name', type=str,
                        required=True, dest='schema_name',
                        help='A brief and meaningful name that '
                             'should help understand the type and content '
                             'of the schema.')

    parser.add_argument('-lp', '--loci-prefix', type=str,
                        required=True, dest='loci_prefix',
                        help='Prefix included in the name of each locus of '
                             'the schema.')

    parser.add_argument('--df', '--description-file', type=str,
                        required=False, dest='description_file', default=None,
                        help='Path to a text file with a description '
                             'about the schema. Markdown syntax is supported '
                             'in order to offer greater customizability of '
                             'the rendered description in the Frontend. '
                             'Will default to the schema\'s name if the user '
                             'does not provide a valid path for a file.')

    parser.add_argument('--a', '--annotations', type=str,
                        required=False, dest='annotations', default=None,
                        help='Path to a TSV file with loci annotations. '
                             'The first column has loci identifiers '
                             '(w/o .fasta extension), the second has user '
                             'annotations and the third has custom '
                             'annotations.')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, dest='cpu_cores', default=1,
                        help='Number of CPU cores/threads that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total'
                             'number of available CPU cores/threads). '
                             'This value will be used to accelerate the '
                             'quality control step that checks all alleles '
                             'in the schema.')

    parser.add_argument('--ns', '--nomenclature-server', type=pv.validate_ns_url,
                        required=False, default='main', dest='nomenclature_server',
                        help='The base URL for the Chewie-NS instance. '
                             'The default value, "main", will establish a '
                             'connection to "https://chewbbaca.online/", '
                             '"tutorial" to "https://tutorial.chewbbaca.online/" '
                             'and "local" to "http://127.0.0.1:5000/NS/api/" (localhost). '
                             'Users may also provide the IP address to other '
                             'Chewie-NS instances.')

    parser.add_argument('--continue_up', required=False, action='store_true',
                        dest='continue_up',
                        help='Check if the schema upload was interrupted and '
                             'attempt to continue upload.')

    args = parser.parse_args()
    del args.LoadSchema

    upload_schema.main(**vars(args))


@pdt.process_timer
def run_synchronize_schema():
    """Run the SyncSchema module to synchronize a local schema with the remote version in Chewie-NS."""

    def msg(name=None):
        # simple command to synchronize a schema with its NS version
        simple_cmd = ('  chewBBACA.py SyncSchema -sc <schema_directory> ')

        # command to synchronize a schema with its NS version with non-default arguments values
        params_cmd = ('  chewBBACA.py SyncSchema -sc <schema_directory> '
                      '--cpu <cpu_cores> '
                      '--ns <nomenclature_server_url>')

        # command to submit novel local alleles
        submit_cmd = (
            '  chewBBACA.py SyncSchema -sc <schema_directory> --submit')

        usage_msg = ('\nSync schema:\n{0}\n'
                     '\nSync schema with non-default parameters:\n{1}\n'
                     '\nSync schema and send novel local alleles to the NS:\n{2}\n'.format(simple_cmd, params_cmd, submit_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='SyncSchema',
                                     description='Synchronize a local schema, previously '
                                                 'downloaded from Chewie-NS, with its latest '
                                                 'version in Chewie-NS.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('SyncSchema', nargs='+',
                        help='')

    parser.add_argument('-sc', '--schema-directory', type=str,
                        required=True, dest='schema_directory',
                        help='Path to the directory with the schema to be '
                             'synced.')

    parser.add_argument('--cpu', '--cpu-cores', type=pv.verify_cpu_usage,
                        required=False, default=1, dest='cpu_cores',
                        help='Number of CPU cores/threads that will be '
                             'used to run the process '
                             '(will be redefined to a lower value '
                             'if it is equal to or exceeds the total'
                             'number of available CPU cores/threads). '
                             'This value will only be used if the process '
                             'retrieves novel alleles from the remote '
                             'schema and needs to redetermine the set '
                             'of representative alleles.')

    parser.add_argument('--ns', '--nomenclature-server', type=pv.validate_ns_url,
                        required=False, default=None, dest='nomenclature_server',
                        help='The base URL for the Chewie-NS instance. '
                             'The default option will get the base URL from the '
                             'schema\'s URI. It is also possible to specify other '
                             'options that are available in chewBBACA\'s configs, '
                             'such as: "main" will establish a connection to '
                             '"https://chewbbaca.online/", "tutorial" to '
                             '"https://tutorial.chewbbaca.online/" and "local" '
                             'to "http://127.0.0.1:5000/NS/api/" (localhost). '
                             'Users may also provide the IP address to other '
                             'Chewie-NS instances.')

    parser.add_argument('--b', '--blast-path', type=pv.check_blast,
                        required=False, default='', dest='blast_path',
                        help='Path to the directory that contains the '
                             'BLAST executables.')

    parser.add_argument('--submit', required=False,
                        action='store_true', dest='submit',
                        help='If the process should identify new alleles '
                             'in the local schema and send them to the '
                             'NS. (only authorized users can submit '
                             'new alleles).')

    # parser.add_argument('--update-profiles', required=False,
    #                     action='store_true', dest='update_profiles',
    #                     help='If the process should update local profiles '
    #                          'stored in the SQLite database.')

    args = parser.parse_args()
    del args.SyncSchema

    synchronize_schema.main(**vars(args))


@pdt.process_timer
def run_stats_requests():
    """Run the NSStats module to get information about schemas in Chewie-NS."""

    def msg(name=None):
        # simple command to list species and totals
        simple_cmd = ('  chewBBACA.py NSStats -m species ')

        # command to list all schemas for a species
        schemas_cmd = ('  chewBBACA.py NSStats -m schemas --sp <species_id> ')

        # command to get information about a single schema
        schema_cmd = ('  chewBBACA.py NSStats -m schemas --sp <species_id> '
                      '--sc <schema_id>')

        usage_msg = ('\nList species and totals:\n{0}\n'
                     '\nList all schemas for a species and associated information:\n{1}\n'
                     '\nGet information about a particular schema:\n{2}\n'
                     ''.format(simple_cmd, schemas_cmd, schema_cmd))

        return usage_msg

    parser = argparse.ArgumentParser(prog='NSStats',
                                     description='Retrieve basic information '
                                                 'about the species and schemas in '
                                                 'a Chewie-NS instance.',
                                     usage=msg(),
                                     formatter_class=ModifiedHelpFormatter)

    parser.add_argument('NSStats', nargs='+',
                        help='')

    parser.add_argument('-m', '--mode', type=str,
                        required=True, dest='mode',
                        choices=['species', 'schemas'],
                        help='The process can retrieve the list of species '
                             '("species" option) in Chewie-NS or the '
                             'list of schemas for a species '
                             '("schemas" option).')

    parser.add_argument('--sp', '--species-id', type=str,
                        required=False, dest='species_id', default=None,
                        help='The integer identifier of a '
                             'species in Chewie-NS.')

    parser.add_argument('--sc', '--schema-id', type=str,
                        required=False, dest='schema_id', default=None,
                        help='The integer identifier of a schema in '
                             'Chewie-NS.')

    parser.add_argument('--ns', '--nomenclature-server', type=pv.validate_ns_url,
                        required=False, default='main', dest='nomenclature_server',
                        help='The base URL for the Chewie-NS instance. '
                             'The default value, "main", will establish a '
                             'connection to "https://chewbbaca.online/", '
                             '"tutorial" to "https://tutorial.chewbbaca.online/" '
                             'and "local" to "http://127.0.0.1:5000/NS/api/" (localhost). '
                             'Users may also provide the IP address to other '
                             'Chewie-NS instances.')

    args = parser.parse_args()
    del args.NSStats

    stats_requests.main(**vars(args))


def main():

    functions_info = {'CreateSchema': ['Create a gene-by-gene schema based on '
                                       'a set of genome assemblies or coding sequences.',
                                       run_create_schema],
                      'AlleleCall': ['Determine the allelic profiles of a set of '
                                     'bacterial genomes based on a schema.',
                                     run_allele_call],
                      'SchemaEvaluator': ['Build an interactive report for schema evaluation.',
                                          run_evaluate_schema],
                      'AlleleCallEvaluator': ['Build an interactive report for allele calling results evaluation.',
                                              run_evaluate_calls],
                      'ExtractCgMLST': ['Determines the set of '
                                        'loci that constitute the '
                                        'core genome based on loci '
                                        'presence thresholds.',
                                        run_determine_cgmlst],
                      'RemoveGenes': ['Remove a list of loci from '
                                      'your allele call output.',
                                      run_remove_genes],
                      'PrepExternalSchema': ['Adapt an external schema to be '
                                             'used with chewBBACA.',
                                             run_adapt_schema],
                      'JoinProfiles': ['Join allele calling results from '
                                       'different runs.',
                                       run_join_profiles],
                      'UniprotFinder': ['Retrieve annotations for loci in a schema.',
                                        run_annotate_schema],
                      'DownloadSchema': ['Download a schema from Chewie-NS.',
                                         run_download_schema],
                      'LoadSchema': ['Upload a schema to Chewie-NS.',
                                     run_upload_schema],
                      'SyncSchema': ['Synchronize a schema with its remote version '
                                     'in Chewie-NS.',
                                     run_synchronize_schema],
                      'NSStats': ['Retrieve basic information about the species '
                                  'and schemas in Chewie-NS.',
                                  run_stats_requests]}

    matches = ["--v", "-v", "-version", "--version"]
    if len(sys.argv) > 1 and any(m in sys.argv[1] for m in matches):
        # Print version and exit
        print('chewBBACA version: {0}'.format(version))
        sys.exit(0)

    print('\nchewBBACA version: {0}'.format(version))
    print('Authors: {0}'.format(ct.authors))
    print('Github: {0}'.format(ct.repository))
    print('Documentation: {0}'.format(ct.documentation))
    print('Contacts: {0}\n'.format(ct.contacts))

    # Display help message if selected process is not valid
    if len(sys.argv) == 1 or sys.argv[1] not in functions_info:
        print('USAGE: chewBBACA.py [module] -h \n')
        print('Select one of the following modules :\n')
        for f in functions_info:
            print('{0}: {1}'.format(f, functions_info[f][0]))
        sys.exit(0)

    # Check python version
    python_version = pv.validate_python_version()

    process = sys.argv[1]
    functions_info[process][1]()


if __name__ == "__main__":

    main()
