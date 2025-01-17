#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Purpose
-------

This module enables the creation of a whole genome multi locus sequence
typing (wgMLST) schema seed.

Expected input
--------------

The process expects the following variables whether through command line
execution or invocation of the :py:func:`main` function:

- ``-i``, ``input_files`` : Path to the directory that contains the input
  FASTA files. Alternatively, a single file with a list of paths to FASTA
  files, one per line.

    - e.g.: ``/home/user/genomes``

- ``-o``, ``output_directory`` : Output directory where the process will
  store intermediate files and create the schema's directory.

    - e.g.: ``/home/user/schemas/new_schema``

- ``--n``, ``schema_name`` : Name given to the folder that will store the
  schema files.

    - e.g.: ``my_schema``

- ``--ptf``, ``ptf_path`` : Path to the Prodigal training file.

    - e.g.: ``/home/user/training_files/species.trn``

- ``--bsr``, ``blast_score_ratio`` : BLAST Score Ratio value.

    - e.g.: ``0.6``

- ``--l``, ``minimum_length`` : Minimum sequence length. Coding sequences
  shorter than this value are excluded.

    - e.g.: ``201``

- ``--t``, ``translation_table`` : Genetic code used to predict genes and
  to translate coding sequences.

    - e.g.: ``11``

- ``--st``, ``size_threshold`` : CDS size variation threshold. Added to the
  schema's config file and used to identify alleles with a length value that
  deviates from the locus length mode during the allele calling process.

    - e.g.: ``0.2``

- ``--w``, ``word_size`` : word size used to generate k-mers during the
  clustering step.

    - e.g.: ``5``

- ``--ws``, ``window_size`` : window size value. Number of consecutive
  k-mers included in each window to determine a minimizer.

    - e.g.: ``5``

- ``--cs``, ``clustering_sim`` : clustering similarity threshold. Minimum
  decimal proportion of shared distinct minimizers for a sequence to be
  added to a cluster.

    - e.g.: ``0.2``

- ``--rf``, ``representative_filter`` : representative similarity threshold.
  Clustered sequences are excluded if they share this proportion of distinct
  minimizers with the cluster representative.

    - e.g.: ``0.9``

- ``--if``, ``intra_filter`` : intra-cluster similarity threshold. Clustered
  sequences are excluded if they share this proportion of distinct minimizers
  with another clustered sequence of equal or greater length.

    - e.g.: ``0.9``

- ``--cpu``, ``cpu_cores`` : Number of CPU cores used to run the process.

    - e.g.: ``4``

- ``--b``, ``blast_path`` : Path to the BLAST executables.

    - e.g.: ``/home/software/blast``

- ``--pm``, ``prodigal_mode`` : Prodigal running mode.

    - e.g.: ``single``

- ``--CDS``, ``cds_input`` : If provided, input is a single or several FASTA
  files with coding sequences (skips gene prediction and CDS extraction).

    - e.g.: ``/home/user/coding_sequences_files``

- ``--no-cleanup``, ``no_cleanup`` : If provided, intermediate files
  generated during process execution are not removed at the end.

Code documentation
------------------
"""


import os
import sys
import math

try:
    from utils import (constants as ct,
                       blast_wrapper as bw,
                       core_functions as cf,
                       file_operations as fo,
                       fasta_operations as fao,
                       sequence_manipulation as sm,
                       iterables_manipulation as im,
                       multiprocessing_operations as mo)
except ModuleNotFoundError:
    from CHEWBBACA.utils import (constants as ct,
                                 blast_wrapper as bw,
                                 core_functions as cf,
                                 file_operations as fo,
                                 fasta_operations as fao,
                                 sequence_manipulation as sm,
                                 iterables_manipulation as im,
                                 multiprocessing_operations as mo)


def create_schema_structure(schema_seed_fasta, output_directory, schema_name):
    """Create the schema directory structure.

    Creates the schema seed directory with one FASTA file per
    distinct locus and the `short` directory with the FASTA files
    used to save the representative sequences.

    Parameters
    ----------
    schema_seed_fasta : str
        Path to the FASTA file that contains the sequences that
        constitute the schema seed. Each FASTA record in the file
        is a representative sequence chosen for a locus.
    output_directory : str
        Path to the main output directory of the process.
    schema_name : str
        Name for the schema's directory.

    Returns
    -------
    schema_files : list
        List with the paths to the FASTA files in the schema seed.
    """
    schema_dir = fo.join_paths(output_directory, [schema_name])
    fo.create_directory(schema_dir)

    # add allele identifier to all sequences
    schema_records = {im.replace_multiple_characters(rec.id, ct.CHAR_REPLACEMENTS): str(rec.seq)
                      for rec in fao.sequence_generator(schema_seed_fasta)}

    loci_basenames = {k: k+'.fasta' for k in schema_records}
    loci_paths = {k: fo.join_paths(schema_dir, [v])
                  for k, v in loci_basenames.items()}

    for k, v in schema_records.items():
        current_representative = fao.fasta_str_record(ct.FASTA_RECORD_TEMPLATE, [k+'_1', v])
        fo.write_to_file(current_representative, loci_paths[k], 'w', '\n')

    # create 'short' directory
    fo.create_short(loci_paths.values(), schema_dir)

    return loci_paths


def create_schema_seed(fasta_files, output_directory, schema_name, ptf_path,
                       blast_score_ratio, minimum_length, translation_table,
                       size_threshold, word_size, window_size, clustering_sim,
                       representative_filter, intra_filter, cpu_cores, blast_path,
                       prodigal_mode, cds_input):
    """Create a schema seed based on a set of input FASTA files."""
    # Map full paths to unique identifier (prefix before first '.')
    input_basenames = im.mapping_function(fasta_files,
                                           fo.file_basename, [False])
    input_basenames = {k: fo.split_joiner(v, [0], '.')
                        for k, v in input_basenames.items()}

    # Detect if some inputs share the same unique prefix
    basename_list = list(input_basenames.values())
    if len(set(basename_list)) < len(fasta_files):
        basename_counts = [[basename, basename_list.count(basename)]
                           for basename in set(basename_list)]
        repeated_basenames = ['{0}: {1}'.format(*l)
                              for l in basename_counts if l[1] > 1]
        sys.exit('\nSome input files share the same filename prefix '
                 '(substring before the first "." in the filename). '
                 'Please make sure that every input file has a unique '
                 'filename prefix.\n{0}'.format('\n'.join(repeated_basenames)))

    # define directory for temporary files
    temp_directory = fo.join_paths(output_directory, ['temp'])
    fo.create_directory(temp_directory)

    cds_path = fo.join_paths(temp_directory, ['2_cds_files'])
    fo.create_directory(cds_path)
    if cds_input is False:
        print('Number of inputs: {0}'.format(len(fasta_files)))

        # create directory to store files with Pyrodigal results
        pyrodigal_path = fo.join_paths(temp_directory, ['1_cds_prediction'])
        fo.create_directory(pyrodigal_path)

        # Run Pyrodigal to predict genes for all input genomes
        print('\n== CDS prediction ==\n')
        print('Predicting CDS for {0} inputs...'.format(len(fasta_files)))
        pyrodigal_results = cf.predict_genes(input_basenames, ptf_path,
                                             translation_table, prodigal_mode,
                                             cpu_cores, pyrodigal_path)

        failed, total_extracted, cds_fastas, cds_coordinates, cds_counts = pyrodigal_results
        if len(failed) > 0:
            print('\nFailed to predict genes for {0} genomes'
                  '.'.format(len(failed)))
            print('Make sure that Prodigal runs in meta mode (--pm meta) '
                  'if any input file has less than 100kbp.')
        if len(cds_fastas) == 0:
            sys.exit('\nCould not predict gene sequences from any '
                     'of the input files.\nPlease provide input files '
                     'in the accepted FASTA format.')

        print('\nExtracted a total of {0} CDS from {1} '
              'inputs.'.format(total_extracted, len(fasta_files)))
    # Inputs are Fasta files with the predicted CDSs
    else:
        # Rename the CDSs in each file based on the input unique identifiers
        print('\nRenaming coding sequences for {0} '
              'input files...'.format(len(input_basenames)))

        renaming_inputs = []
        cds_fastas = []
        for k, v in input_basenames.items():
            output_file = fo.join_paths(cds_path, [f'{v}.fasta'])
            cds_prefix = f'{v}-protein'
            renaming_inputs.append([k, output_file, 1, 50000,
                                    cds_prefix, False, fao.integer_headers])
            cds_fastas.append(output_file)

        # rename CDSs in files
        renaming_results = mo.map_async_parallelizer(renaming_inputs,
                                                     mo.function_helper,
                                                     cpu_cores,
                                                     show_progress=False)

        # no inputs failed gene prediction
        failed = []
        # cannot get CDS coordinates if skipping gene prediction
        cds_coordinates = {}

        cds_counts = sum([r[1] for r in renaming_results])
        print('Input files contain a total of {0} '
              'coding sequences.'.format(cds_counts))

    # Write Prodigal stderr for inputs that failed gene prediction
    if len(failed) > 0:
        # Exclude inputs that failed gene prediction
        input_basenames = im.prune_dictionary(input_basenames, failed.keys())
        # Write Prodigal stderr for inputs that failed gene prediction
        failed_lines = [f'{k}\t{v}' for k, v in failed.items()]
        failed_outfile = fo.join_paths(output_directory,
                                       ['gene_prediction_failures.tsv'])
        fo.write_lines(failed_lines, failed_outfile)

    # Map input identifiers to integers
    # Use the mapped integers to refer to each input
    # This reduces memory usage compared to using string identifiers
    basename_map = im.integer_mapping(input_basenames.values())
    basename_inverse_map = im.invert_dictionary(basename_map)

    # Divide input FASTA files into 15 sublists
    num_chunks = 15
    concatenation_inputs = im.divide_list_into_n_chunks(cds_fastas,
                                                        num_chunks)
    file_index = 1
    cds_files = []
    for group in concatenation_inputs:
        output_file = fo.join_paths(cds_path,
                                    ['coding_sequences_{0}.fasta'.format(file_index)])
        fo.concatenate_files(group, output_file)
        cds_files.append(output_file)
        file_index += 1
        # delete individual FASTA files to release disk space
        fo.remove_files(group)

    # Create directory to store files from pre-process steps
    preprocess_dir = fo.join_paths(temp_directory, ['3_cds_preprocess'])
    fo.create_directory(preprocess_dir)

    # DNA sequences deduplication step
    # keep hash of unique sequences and a list with the integer
    # identifiers of genomes that have those sequences
    # lists of integers are encoded with polyline algorithm
    print('\nRemoving duplicated DNA sequences...', end='')
    # create directory to store files from DNA deduplication
    dna_dedup_dir = fo.join_paths(preprocess_dir, ['cds_deduplication'])
    fo.create_directory(dna_dedup_dir)
    distinct_dna_template = 'distinct_cds_{0}'
    ds_results = cf.exclude_duplicates(cds_files, dna_dedup_dir, cpu_cores,
                                       distinct_dna_template, [basename_map, basename_inverse_map],
                                       False, True)

    distinct_seqids, distinct_file, repeated = ds_results
    print('removed {0} sequences.'.format(int(repeated)))

    print('Kept {0} distinct sequences.'.format(len(distinct_seqids)))

    indexed_dna_file = fao.index_fasta(distinct_file)

    # determine small sequences step
    print('\nRemoving sequences smaller than {0} '
          'nucleotides...'.format(minimum_length), end='')
    ss_results = cf.exclude_small(distinct_file, minimum_length)
    small_seqids, ss_lines = ss_results
    print('removed {0} sequences.'.format(len(small_seqids)))

    # exclude seqids of small sequences
    schema_seqids = list(set(distinct_seqids) - set(small_seqids))
    schema_seqids = im.sort_iterable(schema_seqids, sort_key=lambda x: x.lower())

    # sequence translation step
    cds_translation_dir = fo.join_paths(preprocess_dir, ['cds_translation'])
    fo.create_directory(cds_translation_dir)
    print('Translating {0} CDS...'.format(len(schema_seqids)))
    ts_results = cf.translate_sequences(schema_seqids, distinct_file,
                                        cds_translation_dir, translation_table,
                                        minimum_length, cpu_cores)
    protein_file, ut_seqids, ut_lines = ts_results
    print('\nIdentified {0} CDS that could not be translated.'.format(len(ut_seqids)))

    # write info about invalid alleles to file
    invalid_alleles_file = fo.join_paths(output_directory,
                                         ['invalid_cds.txt'])
    invalid_alleles = im.join_list(ut_lines+ss_lines, '\n')
    fo.write_to_file(invalid_alleles, invalid_alleles_file, 'w', '\n')
    print('\nInfo about untranslatable and small sequences '
          'stored in {0}'.format(invalid_alleles_file))

    # protein sequences deduplication step
    # create directory to store files from protein deduplication
    print('\nRemoving duplicated protein sequences...', end='')
    protein_dedup_dir = fo.join_paths(preprocess_dir,
                                      ['translated_cds_deduplication'])
    fo.create_directory(protein_dedup_dir)
    distinct_prot_template = 'distinct_translated_cds_{0}'
    ds_results = cf.exclude_duplicates([protein_file], protein_dedup_dir, 1,
                                       distinct_prot_template,
                                       [basename_map, basename_inverse_map],
                                       True, True)

    distinct_protein_seqs, distinct_prots_file, repeated = ds_results

    schema_seqids = im.sort_iterable(distinct_protein_seqs,
                                     sort_key=lambda x: x.lower())

    print('removed {0} sequences.'.format(int(repeated)))
    print('\nKept {0} sequences after filtering the initial '
          'sequences.'.format(len(distinct_protein_seqs)))

    # protein clustering step
    # read protein sequences
    proteins = fao.import_sequences(distinct_prots_file)

    # create directory to store clustering data
    clustering_dir = fo.join_paths(temp_directory, ['4_clustering'])
    fo.create_directory(clustering_dir)

    print('Clustering proteins...')
    group_size = math.ceil(len(proteins)/40)
    cs_results = cf.cluster_sequences(proteins, word_size, window_size,
                                      clustering_sim, None, True,
                                      1, 1, clustering_dir, cpu_cores,
                                      group_size, False)
    print('\nClustered {0} proteins into {1} clusters.'
          ''.format(len(proteins), len(cs_results)))

    # exclude based on high similarity to cluster representatives
    rep_filter_dir = fo.join_paths(clustering_dir, ['representative_filter'])
    fo.create_directory(rep_filter_dir)
    print('Removing sequences based on high similarity with the '
          'cluster representative...', end='')
    cp_results = cf.cluster_representative_filter(cs_results,
                                                  representative_filter,
                                                  rep_filter_dir)
    clusters, excluded_seqids, singletons, clustered_sequences = cp_results
    print('removed {0} sequences.'.format(len(excluded_seqids)))
    print('Identified {0} singletons.'.format(len(singletons)))
    print('Remaining sequences after representative and singleton '
          'pruning: {0}'.format(clustered_sequences))

    # remove excluded seqids
    schema_seqids = list(set(schema_seqids) - excluded_seqids)

    # exclude based on high similarity to other clustered sequences
    intra_filter_dir = fo.join_paths(clustering_dir, ['intracluster_filter'])
    fo.create_directory(intra_filter_dir)
    print('Removing sequences based on high similarity with '
          'other clustered sequences...', end='')
    cip_results = cf.cluster_intra_filter(clusters, proteins,
                                          word_size, intra_filter,
                                          intra_filter_dir)
    clusters, intra_excluded = cip_results
    print('removed {0} sequences.'.format(len(intra_excluded)))

    # remove excluded seqids - we get set of sequences from clusters
    # plus singletons
    schema_seqids = list(set(schema_seqids) - set(intra_excluded))

    # define BLASTp and makeblastdb paths
    blastp_path = fo.join_paths(blast_path, [ct.BLASTP_ALIAS])
    makeblastdb_path = fo.join_paths(blast_path, [ct.MAKEBLASTDB_ALIAS])

    if len(clusters) > 0:
        blasting_dir = fo.join_paths(clustering_dir, ['cluster_BLASTer'])
        fo.create_directory(blasting_dir)

        print('Clusters to BLAST: {0}'.format(len(clusters)))
        blast_results, ids_dict = cf.blast_clusters(clusters, proteins,
                                                    blasting_dir, blastp_path,
                                                    makeblastdb_path, cpu_cores)

        blast_files = im.flatten_list(blast_results)

        # compute and exclude based on BSR
        blast_excluded_alleles = [sm.apply_bsr(fo.read_tabular(file),
                                               indexed_dna_file,
                                               blast_score_ratio,
                                               ids_dict)
                                  for file in blast_files]

        # merge bsr results
        blast_excluded_alleles = im.flatten_list(blast_excluded_alleles)

        blast_excluded_alleles = set([ids_dict[seqid] for seqid in blast_excluded_alleles])
        schema_seqids = list(set(schema_seqids) - blast_excluded_alleles)
        print('\n\nRemoved {0} sequences based on high BSR value with '
              'other sequences.'.format(len(blast_excluded_alleles)))

        # write list of excluded to file
        blast_excluded_outfile = fo.join_paths(blasting_dir, ['excluded.txt'])
        fo.write_lines(blast_excluded_alleles, blast_excluded_outfile)

    # perform final BLAST to identify similar sequences that do not
    # share many/any kmers
    print('Total of {0} sequences to compare in final BLAST.'.format(len(schema_seqids)))

    # sort seqids before final BLASTp to ensure consistent results
    schema_seqids = im.sort_iterable(schema_seqids, sort_key=lambda x: x.lower())

    # Create directory for final BLASTp
    final_blast_dir = fo.join_paths(temp_directory, ['5_final_blast'])
    fo.create_directory(final_blast_dir)

    # Create FASTA file with remaining sequences
    beta_file = os.path.join(final_blast_dir, 'remaining_sequences.fasta')
    fao.get_sequences_by_id(proteins, schema_seqids, beta_file)

    # Change sequence identifiers to avoid BLAST error
    # related to sequence header ength limite
    integer_seqids = os.path.join(final_blast_dir, 'remaining_sequences_integer_headers.fasta')
    ids_dict2 = fao.integer_headers(beta_file, integer_seqids, prefix='seq_')

    # Create BLASTp database
    blast_db = fo.join_paths(final_blast_dir, ['remaining_sequences'])
    db_stderr = bw.make_blast_db(makeblastdb_path, integer_seqids, blast_db, 'prot')

    if len(db_stderr) > 0:
        sys.exit(db_stderr)

    # Divide FASTA file into groups of 100 sequences to reduce
    # execution time for large sequence sets
    split_dir = fo.join_paths(final_blast_dir, ['cds_subsets'])
    fo.create_directory(split_dir)
    splitted_fastas = fao.split_seqcount(integer_seqids, split_dir, 100)

    # Create directory to store results from final BLASTp
    final_blastp_dir = fo.join_paths(final_blast_dir, ['BLAST_results'])
    fo.create_directory(final_blastp_dir)
    blast_outputs = ['{0}/{1}_blast_out.tsv'.format(final_blastp_dir,
                                                    fo.file_basename(i[0], False))
                     for i in splitted_fastas]

    # Add common arguments to all sublists
    blast_inputs = [[blastp_path, blast_db, file[0],
                     blast_outputs[i], 1, 1, bw.run_blast]
                    for i, file in enumerate(splitted_fastas)]

    print('Performing final BLASTp...')
    blast_stderr = mo.map_async_parallelizer(blast_inputs,
                                             mo.function_helper,
                                             cpu_cores,
                                             show_progress=True)

    blast_stderr = im.flatten_list(blast_stderr)
    if len(blast_stderr) > 0:
        sys.exit(blast_stderr)

    # Concatenate files with BLASTp results
    blast_output = fo.join_paths(final_blast_dir, ['blast_out_concat.tsv'])
    blast_output = fo.concatenate_files(blast_outputs, blast_output)

    final_excluded = sm.apply_bsr(fo.read_tabular(blast_output),
                                  indexed_dna_file,
                                  blast_score_ratio,
                                  ids_dict2)
    final_excluded = [ids_dict2[seqid] for seqid in final_excluded]

    schema_seqids = list(set(schema_seqids) - set(final_excluded))

    print('\nRemoved {0} sequences that were highly similar '
          'to other sequences.'.format(len(final_excluded)))

    # Create file with the schema representative sequences
    loci_representatives = os.path.join(final_blast_dir, 'loci_representatives.fasta')
    fao.get_sequences_by_id(indexed_dna_file, schema_seqids, loci_representatives)

    schema_files = create_schema_structure(loci_representatives, output_directory,
                                           schema_name)

    # Create file with CDSs coordinates
    # Will not be created if input files contain predicted CDS
    if cds_input is False:
        files = []
        for gid, file in cds_coordinates.items():
            tsv_file = fo.join_paths(temp_directory, [f'{gid}.tsv'])
            cf.write_coordinates_file(file, tsv_file)
            files.append(tsv_file)
        # Concatenate all TSV files with CDS coordinates
        cds_coordinates = fo.join_paths(output_directory,
                                        [ct.CDS_COORDINATES_BASENAME])
        fo.concatenate_files(files, cds_coordinates,
                             header=ct.CDS_TABLE_HEADER)

    return [schema_files, temp_directory]


def main(input_files, output_directory, schema_name, ptf_path,
         blast_score_ratio, minimum_length, translation_table,
         size_threshold, word_size, window_size, clustering_sim,
         representative_filter, intra_filter, cpu_cores, blast_path,
         cds_input, prodigal_mode, no_cleanup):

    print(f'Prodigal training file: {ptf_path}')
    print(f'Prodigal mode: {prodigal_mode}')
    print(f'CPU cores: {cpu_cores}')
    print(f'BLAST Score Ratio: {blast_score_ratio}')
    print(f'Translation table: {translation_table}')
    print(f'Minimum sequence length: {minimum_length}')
    print(f'Size threshold: {size_threshold}')
    print(f'Word size: {word_size}')
    print(f'Window size: {window_size}')
    print(f'Clustering similarity: {clustering_sim}')
    print(f'Representative filter: {representative_filter}')
    print(f'Intra-cluster filter: {intra_filter}')

    if prodigal_mode == 'meta' and ptf_path is not None:
        print('Prodigal mode is set to "meta". Will add training file to '
              'the schema, but will not use it for gene prediction during '
              'schema creation.')
        ptf_path = None

    # Read file with paths to input files
    input_files = fo.read_lines(input_files, strip=True)

    # Sort paths to FASTA files
    input_files = im.sort_iterable(input_files, sort_key=lambda x: x.lower())

    results = create_schema_seed(input_files, output_directory, schema_name,
                                 ptf_path, blast_score_ratio, minimum_length,
                                 translation_table, size_threshold, word_size,
                                 window_size, clustering_sim, representative_filter,
                                 intra_filter, cpu_cores, blast_path,
                                 prodigal_mode, cds_input)

    # Remove temporary files
    if no_cleanup is False:
        exists = fo.delete_directory(results[1])

    # Print message about schema that was created
    print('Created schema seed with {0} loci.'.format(len(results[0])))
