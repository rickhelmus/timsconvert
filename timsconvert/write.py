from timsconvert.parse import *
from timsconvert.classes import *
import os
import logging
import numpy as np
from psims.mzml import MzMLWriter
from pyimzml.ImzMLWriter import ImzMLWriter
from pyimzml.compression import NoCompression, ZlibCompression


def write_mzml_metadata(data, writer, infile, mode, ms2_only, barebones_metadata):
    """
    Write metadata to mzML file using psims. Includes spectral metadata, source files, software list, instrument
    configuration, and data processing. Note that TIMSCONVERT is not included as a data processing step due to a lack
    CV param and compatibility with downstream data analysis software.

    :param data: Object containing raw data information from TDF, TSF, or BAF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData |
        timsconvert.classes.TimsconvertBafData
    :param writer: Instance of psims.mzml.MzMLWriter for output file.
    :type writer: psims.mzml.MzMLWriter
    :param infile: Input file path to be used for source file metadata.
    :type infile: str
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param barebones_metadata: If True, omit software and data processing metadata in the resulting mzML files. Used
        for compatibility with downstream analysis software that does not have support for newer CV params or
        UserParams.
    :type barebones_metadata: bool
    """
    # Basic file descriptions.
    file_description = []
    if isinstance(data, TimsconvertBafData):
        metadata_key = 'Properties'
    elif isinstance(data, TimsconvertTsfData) or isinstance(data, TimsconvertTdfData):
        metadata_key = 'GlobalMetadata'
    # Add spectra level and centroid/profile status.
    if isinstance(data, TimsconvertBafData):
        ms_levels = list(set(data.analysis['AcquisitionKeys']['MsLevel'].values.tolist()))
        ms_levels = [int(i) for i in ms_levels]
        if 0 in ms_levels:
            file_description.append('MS1 spectrum')
        if 1 in ms_levels:
            file_description.append('MSn spectrum')
    elif isinstance(data, TimsconvertTsfData) or isinstance(data, TimsconvertTdfData):
        ms_levels = list(set(data.analysis['Frames']['MsMsType'].values.tolist()))
        ms_levels = [int(i) for i in ms_levels]
        ms_levels_tmp = []
        for i in ms_levels:
            if i in MSMS_TYPE_CATEGORY['ms1']:
                ms_levels_tmp.append('MS1 spectrum')
            elif i in MSMS_TYPE_CATEGORY['ms2']:
                ms_levels_tmp.append('MSn spectrum')
        ms_levels_tmp = list(set(ms_levels_tmp))
        for i in ms_levels_tmp:
            file_description.append(i)
    else:
        if not ms2_only:
            file_description.append('MS1 spectrum')
            file_description.append('MSn spectrum')
        elif ms2_only:
            file_description.append('MSn spectrum')
    if mode == 'raw' or mode == 'centroid':
        file_description.append('centroid spectrum')
    elif mode == 'profile':
        file_description.append('profile spectrum')
    # Source file
    sf = writer.SourceFile(os.path.split(infile)[0],
                           os.path.split(infile)[1],
                           id=os.path.splitext(os.path.split(infile)[1])[0])
    writer.file_description(file_contents=file_description, source_files=sf)

    # Add list of software.
    if not barebones_metadata:
        acquisition_software_id = data.analysis[metadata_key]['AcquisitionSoftware']
        acquisition_software_version = data.analysis[metadata_key]['AcquisitionSoftwareVersion']
        if acquisition_software_id == 'Bruker otofControl' or acquisition_software_id == 'timsTOF':
            acquisition_software_params = ['micrOTOFcontrol', ]
        else:
            acquisition_software_params = []
        psims_software = {'id': 'psims-writer',
                          'version': '0.1.2',
                          'params': ['python-psims', ]}
        writer.software_list([{'id': acquisition_software_id,
                               'version': acquisition_software_version,
                               'params': acquisition_software_params},
                              psims_software])

    # Instrument configuration.
    inst_count = 1
    if data.analysis[metadata_key]['InstrumentSourceType'] in INSTRUMENT_SOURCE_TYPE.keys() \
            and 'MaldiApplicationType' not in data.analysis[metadata_key].keys():
        source = writer.Source(inst_count,
                               [INSTRUMENT_SOURCE_TYPE[data.analysis[metadata_key]['InstrumentSourceType']]])
    # If source isn't found in the GlobalMetadata SQL table, hard code source to ESI
    elif 'MaldiApplicationType' in data.analysis[metadata_key].keys():
        source = writer.Source(inst_count, ['matrix-assisted laser desorption ionization'])

    # Analyzer and detector hard coded for timsTOF fleX
    inst_count += 1
    analyzer = writer.Analyzer(inst_count, ['quadrupole', 'time-of-flight'])
    inst_count += 1
    detector = writer.Detector(inst_count, ['electron multiplier'])
    inst_config = writer.InstrumentConfiguration(id='instrument', component_list=[source, analyzer, detector])
    writer.instrument_configuration_list([inst_config])

    # Data processing element.
    if not barebones_metadata:
        proc_methods = [writer.ProcessingMethod(order=1,
                                                software_reference='psims-writer',
                                                params=['Conversion to mzML'])]
        processing = writer.DataProcessing(proc_methods, id='exportation')
        writer.data_processing_list([processing])


def get_spectra_count(data):
    """
    Calculate the predicted number of spectra to be written.

    :param data: Object containing raw data information from TDF, TSF, or BAF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData |
        timsconvert.classes.TimsconvertBafData
    :return: Number of expected spectra.
    :rtype: int
    """
    if isinstance(data, TimsconvertTdfData):
        ms1_count = data.analysis['Frames'][data.analysis['Frames']['MsMsType'] == 0]['MsMsType'].values.size
        if 'Precursors' in data.analysis.keys():
            ms2_count = len(list(filter(None, data.analysis['Precursors']['MonoisotopicMz'].values)))
        # Set ms2_count to 0 if precursors table is not found.
        else:
            ms2_count = 0
        ms_count = ms1_count + ms2_count
    elif isinstance(data, TimsconvertTsfData):
        ms_count = data.analysis['Frames'].shape[0]
    elif isinstance(data, TimsconvertBafData):
        ms1_count = data.analysis['Spectra'][data.analysis['Spectra']['AcquisitionKey'] ==
                                             1]['AcquisitionKey'].values.size
        ms2_count = data.analysis['Spectra'][data.analysis['Spectra']['AcquisitionKey'] ==
                                             2]['AcquisitionKey'].values.size
        ms_count = ms1_count + ms2_count
    return ms_count


def update_spectra_count(outdir, outfile, num_of_spectra, scan_count):
    """
    Calculate the actual number of spectra that were written to the output mzML file. Update is needed to prevent
    counting emtpy spectra that were omitted from the output. Performs this by iterating over tmp mzML file that was
    written and replacing the tmp file with a final mzML file with a true spectra count.

    :param outdir: Output directory path that was specified from the command line parameters or the original input
        file path if no output directory was specified.
    :type outdir: str
    :param outfile: Output filename that was specified from the command line parameters or the original input filename
        if no output filename was specified.
    :type outfile: str
    :param num_of_spectra: Number of spectra that was calculated for the current file being converted using
        timsconvert.write.get_spectra_count().
    :type num_of_spectra: int
    :param scan_count: Final true count for the number of spectra from the current file being converted.
    :type scan_count: int
    """
    if os.path.exists(os.path.join(outdir, outfile)):
        os.remove(os.path.join(outdir, outfile))
    with open(os.path.splitext(os.path.join(outdir, outfile))[0] + '_tmp.mzML', 'r') as in_stream, \
            open(os.path.join(outdir, outfile), 'w') as out_stream:
        for line in in_stream:
            out_stream.write(line.replace('      <spectrumList count="' + str(num_of_spectra) + '" defaultDataProcessingRef="exportation">',
                                          '      <spectrumList count="' + str(scan_count) + '" defaultDataProcessingRef="exportation">'))
    os.remove(os.path.splitext(os.path.join(outdir, outfile))[0] + '_tmp.mzML')


def write_ms1_spectrum(writer, data, scan, encoding, compression, title=None):
    """
    Write an MS1 spectrum to an mzML file using psims.

    :param writer: Instance of psims.mzml.MzMLWriter for output file.
    :type writer: psims.mzml.MzMLWriter
    :param data: Object containing raw data information from TDF, TSF, or BAF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData |
        timsconvert.classes.TimsconvertBafData
    :param scan: Dictionary containing standard spectrum data.
    :type scan: dict
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :param compression: Compression command line parameter, either "zlib" or "none".
    :type compression: str
    :param title: Spectrum title to be used for MALDI data, defaults to None.
    :type title: str | None
    """
    if isinstance(data, TimsconvertBafData):
        metadata_key = 'Properties'
    elif isinstance(data, TimsconvertTsfData) or isinstance(data, TimsconvertTdfData):
        metadata_key = 'GlobalMetadata'
    # Build params list for spectrum.
    params = [scan['scan_type'],
              {'ms level': scan['ms_level']},
              {'total ion current': scan['total_ion_current']},
              {'base peak m/z': scan['base_peak_mz']},
              {'base peak intensity': scan['base_peak_intensity']},
              {'highest observed m/z': scan['high_mz']},
              {'lowest observed m/z': scan['low_mz']}]
    if 'MaldiApplicationType' in data.analysis[metadata_key].keys():
        params.append({'maldi spot identifier': scan['coord']})
        params.append({'spectrum title': title})
    if scan['ms2_no_precursor']:
        params.append({'collision energy': scan['collision_energy']})

    if scan['mobility_array'] is not None:
        # This version only works with newer versions of psims.
        # Currently unusable due to boost::interprocess error on Linux.
        # other_arrays = [({'name': 'mean inverse reduced ion mobility array',
        #                  'unit_name': 'volt-second per square centimeter'},
        #                 parent_scan['mobility_array'])]
        # Need to use older notation with a tuple (name, array) due to using psims 0.1.34.
        other_arrays = [('mean inverse reduced ion mobility array', scan['mobility_array'])]
    else:
        other_arrays = None

    encoding_dict = {'m/z array': get_encoding_dtype(encoding),
                     'intensity array': get_encoding_dtype(encoding)}
    if other_arrays is not None:
        encoding_dict['mean inverse reduced ion mobility array'] = get_encoding_dtype(encoding)

    writer.write_spectrum(scan['mz_array'],
                          scan['intensity_array'],
                          id='scan=' + str(scan['scan_number']),
                          polarity=scan['polarity'],
                          centroided=scan['centroided'],
                          scan_start_time=scan['retention_time'],
                          other_arrays=other_arrays,
                          params=params,
                          encoding=encoding_dict,
                          compression=compression)


def write_ms2_spectrum(writer, data, scan, encoding, compression, parent_scan=None, title=None):
    """
    Write an MS/MS spectrum to an mzML file using psims.

    :param writer: Instance of psims.mzml.MzMLWriter for output file.
    :type writer: psims.mzml.MzMLWriter
    :param data: Object containing raw data information from TDF, TSF, or BAF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData |
        timsconvert.classes.TimsconvertBafData
    :param scan: Dictionary containing standard spectrum data.
    :type scan: dict
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :param compression: Compression command line parameter, either "zlib" or "none".
    :type compression: str
    :param parent_scan: Dictionary containing standard spectrum data for parent scan used to link MS/MS spectrum with
        an MS1 spectrum.
    :type parent_scan: dict | None
    :param title: Spectrum title to be used for MALDI data, defaults to None.
    :type title: str | None
    """
    if isinstance(data, TimsconvertBafData):
        metadata_key = 'Properties'
    elif isinstance(data, TimsconvertTsfData) or isinstance(data, TimsconvertTdfData):
        metadata_key = 'GlobalMetadata'
    # Build params list for spectrum.
    params = [scan['scan_type'],
              {'ms level': scan['ms_level']},
              {'total ion current': scan['total_ion_current']}]
    if 'MaldiApplicationType' in data.analysis[metadata_key].keys():
        params.append({'spectrum title': title})
    if 'base_peak_mz' in scan.keys() and 'base_peak_intensity' in scan.keys():
        params.append({'base peak m/z': scan['base_peak_mz']})
        params.append({'base peak intensity': scan['base_peak_intensity']})
    if 'high_mz' in scan.keys() and 'low_mz' in scan.keys():
        params.append({'highest observed m/z': scan['high_mz']})
        params.append({'lowest observed m/z': scan['low_mz']})

    if scan['mobility_array'] is not None:
        # This version only works with newer versions of psims.
        # Currently unusable due to boost::interprocess error on Linux.
        # other_arrays = [({'name': 'mean inverse reduced ion mobility array',
        #                  'unit_name': 'volt-second per square centimeter'},
        #                 parent_scan['mobility_array'])]
        # Need to use older notation with a tuple (name, array) due to using psims 0.1.34.
        other_arrays = [('mean inverse reduced ion mobility array', scan['mobility_array'])]
    else:
        other_arrays = None

    encoding_dict = {'m/z array': get_encoding_dtype(encoding),
                     'intensity array': get_encoding_dtype(encoding)}
    if other_arrays is not None:
        encoding_dict['mean inverse reduced ion mobility array'] = get_encoding_dtype(encoding)

    # Build precursor information dict.
    precursor_info = {'mz': scan['selected_ion_mz'],
                      'activation': [{'collision energy': scan['collision_energy']}],
                      'isolation_window_args': {'target': scan['target_mz'],
                                                'upper': scan['isolation_upper_offset'],
                                                'lower': scan['isolation_lower_offset']},
                      'params': []}

    if scan['selected_ion_intensity'] is not None:
        precursor_info['intensity'] = scan['selected_ion_intensity']
    if scan['selected_ion_mobility'] is not None:
        precursor_info['params'].append({'inverse reduced ion mobility': scan['selected_ion_mobility']})
    if scan['selected_ion_ccs'] is not None:
        precursor_info['params'].append({'collisional cross sectional area': scan['selected_ion_ccs']})
    if scan['charge_state'] is not None and \
            not np.isnan(scan['charge_state']):
        if int(scan['charge_state']) != 0:
            precursor_info['charge'] = scan['charge_state']

    if parent_scan is not None:
        precursor_info['spectrum_reference'] = 'scan=' + str(parent_scan['scan_number'])

    # Write out MS2 spectrum.
    writer.write_spectrum(scan['mz_array'],
                          scan['intensity_array'],
                          id='scan=' + str(scan['scan_number']),
                          polarity=scan['polarity'],
                          centroided=scan['centroided'],
                          scan_start_time=scan['retention_time'],
                          other_arrays=other_arrays,
                          params=params,
                          precursor_information=precursor_info,
                          encoding=encoding_dict,
                          compression=compression)


def write_lcms_chunk_to_mzml(data, writer, frame_start, frame_stop, scan_count, mode, ms2_only, exclude_mobility,
                             profile_bins, encoding, compression):
    """
    Parse and write out a group of spectra to an mzML file from an LC-MS(/MS) dataset using psims.

    :param data: Object containing raw data information from TDF, TSF, or BAF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData |
        timsconvert.classes.TimsconvertBafData
    :param writer: Instance of psims.mzml.MzMLWriter for output file.
    :type writer: psims.mzml.MzMLWriter
    :param frame_start: Beginning frame number.
    :type frame_start: int
    :param frame_stop: Ending frame number (non-inclusive).
    :type frame_stop: int
    :param scan_count: Current count for the number of spectra from the current file that have been converted.
    :type scan_count: int
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param exclude_mobility: Whether to include mobility data in the output files, defaults to None.
    :type exclude_mobility: bool
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :param compression: Compression command line parameter, either "zlib" or "none".
    :type compression: str
    :return: Updated count for the number of spectra from the current file that have been converted.
    :rtype: int
    """
    # Parse TDF data
    if isinstance(data, TimsconvertTdfData):
        parent_scans, product_scans = parse_lcms_tdf(data,
                                                     frame_start,
                                                     frame_stop,
                                                     mode,
                                                     ms2_only,
                                                     exclude_mobility,
                                                     profile_bins,
                                                     encoding)
    # Parse TSF data
    elif isinstance(data, TimsconvertTsfData):
        parent_scans, product_scans = parse_lcms_tsf(data,
                                                     frame_start,
                                                     frame_stop,
                                                     mode,
                                                     ms2_only,
                                                     profile_bins,
                                                     encoding)
    # Parse BAF data
    elif isinstance(data, TimsconvertBafData):
        parent_scans, product_scans = parse_lcms_baf(data,
                                                     frame_start,
                                                     frame_stop,
                                                     mode,
                                                     ms2_only,
                                                     profile_bins,
                                                     encoding)

    # Write MS1 parent scans.
    if not ms2_only and product_scans != []:
        for parent in parent_scans:
            products = [i for i in product_scans if i['parent_frame'] == parent['frame']]
            # Set params for scan.
            scan_count += 1
            parent['scan_number'] = scan_count
            write_ms1_spectrum(writer, data, parent, encoding, compression)
            # Write MS2 Product Scans
            for product in products:
                scan_count += 1
                product['scan_number'] = scan_count
                write_ms2_spectrum(writer, data, product, encoding, compression, parent_scan=parent)
    elif ms2_only or parent_scans == []:
        for product in product_scans:
            scan_count += 1
            product['scan_number'] = scan_count
            write_ms2_spectrum(writer, data, product, encoding, compression)
    elif not product_scans:
        for scan_dict in parent_scans:
            scan_count += 1
            scan_dict['scan_number'] = scan_count
            if scan_dict['ms_level'] == 1:
                write_ms1_spectrum(writer, data, scan_dict, encoding, compression)
            elif scan_dict['ms_level'] == 2:
                if scan_dict['ms2_no_precursor']:
                    write_ms1_spectrum(writer, data, scan_dict, encoding, compression)
                else:
                    write_ms2_spectrum(writer, data, scan_dict, encoding, compression)
    return scan_count


def write_lcms_mzml(data, infile, outdir, outfile, mode, ms2_only, exclude_mobility, profile_bins, encoding,
                    compression, barebones_metadata, chunk_size):
    """
    Parse and write out spectra to an mzML file from an LC-MS(/MS) dataset using psims.

    :param data: Object containing raw data information from TDF, TSF, or BAF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData |
        timsconvert.classes.TimsconvertBafData
    :param infile: Input file path to be used for source file metadata.
    :type infile: str
    :param outdir: Output directory path that was specified from the command line parameters or the original input
        file path if no output directory was specified.
    :type outdir: str
    :param outfile: Output filename that was specified from the command line parameters or the original input filename
        if no output filename was specified.
    :type outfile: str
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param exclude_mobility: Whether to include mobility data in the output files, defaults to None.
    :type exclude_mobility: bool
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :param compression: Compression command line parameter, either "zlib" or "none".
    :type compression: str
    :param barebones_metadata: If True, omit software and data processing metadata in the resulting mzML files. Used
        for compatibility with downstream analysis software that does not have support for newer CV params or
        UserParams.
    :type barebones_metadata: bool
    :param chunk_size: Number of MS1 spectra that to be used when subsetting dataset into smaller groups to pass onto
        timsconvert.write.write_lcms_chunk_to_mzml() for memory efficiency; larger chunk_size requires more memory
        during conversion.
    :type chunk_size: int
    """
    # Initialize mzML writer using psims.
    logging.info(get_timestamp() + ':' + 'Initializing mzML Writer...')
    writer = MzMLWriter(os.path.splitext(os.path.join(outdir, outfile))[0] + '_tmp.mzML', close=True)

    with writer:
        # Begin mzML with controlled vocabularies (CV).
        logging.info(get_timestamp() + ':' + 'Initializing controlled vocabularies...')
        writer.controlled_vocabularies()

        # Start write acquisition, instrument config, processing, etc. to mzML.
        logging.info(get_timestamp() + ':' + 'Writing mzML metadata...')
        write_mzml_metadata(data, writer, infile, mode, ms2_only, barebones_metadata)

        logging.info(get_timestamp() + ':' + 'Writing data to .mzML file ' + os.path.join(outdir, outfile) + '...')
        # Parse chunks of data and write to spectrum elements.
        with writer.run(id='run', instrument_configuration='instrument'):
            scan_count = 0
            # Count number of spectra in run.
            logging.info(get_timestamp() + ':' + 'Calculating number of spectra...')
            num_of_spectra = get_spectra_count(data)
            with writer.spectrum_list(count=num_of_spectra):
                chunk = 0
                # Write data in chunks of chunks_size.
                while chunk + chunk_size + 1 <= len(data.ms1_frames):
                    chunk_list = []
                    for i, j in zip(data.ms1_frames[chunk: chunk + chunk_size],
                                    data.ms1_frames[chunk + 1: chunk + chunk_size + 1]):
                        chunk_list.append((int(i), int(j)))
                    logging.info(get_timestamp() + ':' + 'Parsing and writing Frame ' + str(chunk_list[0][0]) + '...')
                    for frame_start, frame_stop in chunk_list:
                        scan_count = write_lcms_chunk_to_mzml(data,
                                                              writer,
                                                              frame_start,
                                                              frame_stop,
                                                              scan_count,
                                                              mode,
                                                              ms2_only,
                                                              exclude_mobility,
                                                              profile_bins,
                                                              encoding,
                                                              compression)
                    chunk += chunk_size
                # Last chunk may be smaller than chunk_size
                else:
                    chunk_list = []
                    for i, j in zip(data.ms1_frames[chunk:-1], data.ms1_frames[chunk + 1:]):
                        chunk_list.append((int(i), int(j)))
                    if isinstance(data, TimsconvertBafData):
                        chunk_list.append((j, data.analysis['Spectra'].shape[0] + 1))
                    elif isinstance(data, TimsconvertTsfData) or isinstance(data, TimsconvertTdfData):
                        chunk_list.append((j, data.analysis['Frames'].shape[0] + 1))
                    logging.info(get_timestamp() + ':' + 'Parsing and writing Frame ' + str(chunk_list[0][0]) + '...')
                    for frame_start, frame_stop in chunk_list:
                        scan_count = write_lcms_chunk_to_mzml(data,
                                                              writer,
                                                              frame_start,
                                                              frame_stop,
                                                              scan_count,
                                                              mode,
                                                              ms2_only,
                                                              exclude_mobility,
                                                              profile_bins,
                                                              encoding,
                                                              compression)

    if num_of_spectra != scan_count:
        logging.info(get_timestamp() + ':' + 'Updating scan count...')
        update_spectra_count(outdir, outfile, num_of_spectra, scan_count)
    else:
        logging.info(get_timestamp() + ':' + 'Renaming mzML file...')
        if os.path.exists(os.path.join(outdir, outfile)):
            os.remove(os.path.join(outdir, outfile))
        os.rename(os.path.splitext(os.path.join(outdir, outfile))[0] + '_tmp.mzML', os.path.join(outdir, outfile))
    logging.info(get_timestamp() + ':' + 'Finished writing to .mzML file ' +
                 os.path.join(outdir, outfile) + '...')


def write_maldi_dd_mzml(data, infile, outdir, outfile, mode, ms2_only, exclude_mobility, profile_bins, encoding,
                        compression, maldi_output_file, plate_map, barebones_metadata):
    """
    Parse and write out spectra to an mzML file from a MALDI-MS(/MS) dried droplet dataset using psims.

    :param data: Object containing raw data information from TDF or TSF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData
    :param infile: Input file path to be used for source file metadata.
    :type infile: str
    :param outdir: Output directory path that was specified from the command line parameters or the original input
        file path if no output directory was specified.
    :type outdir: str
    :param outfile: Output filename that was specified from the command line parameters or the original input filename
        if no output filename was specified.
    :type outfile: str
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param exclude_mobility: Whether to include mobility data in the output files, defaults to None.
    :type exclude_mobility: bool
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :param compression: Compression command line parameter, either "zlib" or "none".
    :type compression: str
    :param maldi_output_file: Determines whether all spectra from a given .d dataset are written to a single mzML file
        ("combined"), written to individual mzML files ("individual", i.e. one spectrum per file), or grouped to have
        one mzML file per annotation/label/condition ("sample", requires CSV plate_map to be specified).
    :type maldi_output_file: str
    :param plate_map: Path to the MALDI plate map in CSV format.
    :type plate_map: str
    :param barebones_metadata: If True, omit software and data processing metadata in the resulting mzML files. Used
        for compatibility with downstream analysis software that does not have support for newer CV params or
        UserParams.
    :type barebones_metadata: bool
    """
    if isinstance(data, TimsconvertBafData):
        frames_key = 'Spectra'
        metadata_key = 'Properties'
    elif isinstance(data, TimsconvertTsfData) or isinstance(data, TimsconvertTdfData):
        frames_key = 'Frames'
        metadata_key = 'GlobalMetadata'
    # All spectra from a given TSF or TDF file are combined into a single mzML file.
    if maldi_output_file == 'combined':
        # Initialize mzML writer using psims.
        logging.info(get_timestamp() + ':' + 'Initializing mzML Writer...')
        writer = MzMLWriter(os.path.splitext(os.path.join(outdir, outfile))[0] + '_tmp.mzML', close=True)

        with writer:
            # Begin mzML with controlled vocabularies (CV).
            logging.info(get_timestamp() + ':' + 'Initializing controlled vocabularies...')
            writer.controlled_vocabularies()

            # Start write acquisition, instrument config, processing, etc. to mzML.
            logging.info(get_timestamp() + ':' + 'Writing mzML metadata...')
            write_mzml_metadata(data, writer, infile, mode, ms2_only, barebones_metadata)

            logging.info(get_timestamp() + ':' + 'Writing data to .mzML file ' + os.path.join(outdir, outfile) + '...')
            # Parse chunks of data and write to spectrum element.
            with writer.run(id='run', instrument_configuration='instrument'):
                scan_count = 0
                # Count number of spectra in run.
                logging.info(get_timestamp() + ':' + 'Calculating number of spectra...')
                num_of_spectra = len(data.analysis[frames_key]['Id'].to_list())
                with writer.spectrum_list(count=num_of_spectra):
                    # Parse all MALDI data.
                    num_frames = data.analysis[frames_key].shape[0] + 1
                    # Parse TSF data.
                    if data.analysis[metadata_key]['SchemaType'] == 'TSF':
                        if mode == 'raw':
                            logging.info(get_timestamp() + ':' + 'TSF file detected. Only export in profile or '
                                                                 'centroid mode are supported. Defaulting to centroid '
                                                                 'mode.')
                        list_of_scan_dicts = parse_maldi_tsf(data,
                                                             1,
                                                             num_frames,
                                                             mode,
                                                             ms2_only,
                                                             profile_bins,
                                                             encoding)
                    # Parse TDF data.
                    elif data.analysis[metadata_key]['SchemaType'] == 'TDF':
                        list_of_scan_dicts = parse_maldi_tdf(data,
                                                             1,
                                                             num_frames,
                                                             mode,
                                                             ms2_only,
                                                             exclude_mobility,
                                                             profile_bins,
                                                             encoding)
                    # Write MS1 parent scans.
                    for scan_dict in list_of_scan_dicts:
                        if ms2_only and scan_dict['ms_level'] == 1:
                            pass
                        else:
                            scan_count += 1
                            scan_dict['scan_number'] = scan_count
                            if scan_dict['ms_level'] == 1:
                                write_ms1_spectrum(writer,
                                                   data,
                                                   scan_dict,
                                                   encoding,
                                                   compression,
                                                   title=os.path.splitext(outfile)[0])
                            elif scan_dict['ms_level'] == 2:
                                write_ms2_spectrum(writer,
                                                   data,
                                                   scan_dict,
                                                   encoding,
                                                   compression,
                                                   title=os.path.splitext(outfile)[0])

        logging.info(get_timestamp() + ':' + 'Updating scan count...')
        update_spectra_count(outdir, outfile, num_of_spectra, scan_count)
        logging.info(get_timestamp() + ':' + 'Finished writing to .mzML file ' + os.path.join(outdir, outfile) + '...')

    # Each spectrum in a given TSF or TDF file is output as its own individual mzML file.
    elif maldi_output_file == 'individual' and plate_map != '':
        # Check to make sure plate map is a valid csv file.
        if os.path.exists(plate_map) and os.path.splitext(plate_map)[1] == '.csv':
            # Parse all MALDI data.
            num_frames = data.analysis[frames_key].shape[0] + 1
            # Parse TSF data.
            if data.analysis[metadata_key]['SchemaType'] == 'TSF':
                if mode == 'raw':
                    logging.info(get_timestamp() + ':' + 'TSF file detected. Only export in profile or '
                                                         'centroid mode are supported. Defaulting to centroid '
                                                         'mode.')
                list_of_scan_dicts = parse_maldi_tsf(data,
                                                     1,
                                                     num_frames,
                                                     mode,
                                                     ms2_only,
                                                     profile_bins,
                                                     encoding)
            # Parse TDF data.
            elif data.analysis[metadata_key]['SchemaType'] == 'TDF':
                list_of_scan_dicts = parse_maldi_tdf(data,
                                                     1,
                                                     num_frames,
                                                     mode,
                                                     ms2_only,
                                                     exclude_mobility,
                                                     profile_bins,
                                                     encoding)

            # Use plate map to determine filename.
            # Names things as sample_position.mzML
            plate_map_dict = parse_maldi_plate_map(plate_map)

            for scan_dict in list_of_scan_dicts:
                output_filename = os.path.join(outdir,
                                               plate_map_dict[scan_dict['coord']] + '_' + scan_dict['coord'] + '.mzML')

                writer = MzMLWriter(output_filename, close=True)

                with writer:
                    writer.controlled_vocabularies()

                    write_mzml_metadata(data, writer, infile, mode, ms2_only, barebones_metadata)

                    with writer.run(id='run', instrument_configuration='instrument'):
                        scan_count = 1
                        scan_dict['scan_number'] = scan_count
                        with writer.spectrum_list(count=scan_count):
                            if ms2_only and scan_dict['ms_level'] == 1:
                                pass
                            else:
                                if scan_dict['ms_level'] == 1:
                                    write_ms1_spectrum(writer,
                                                       data,
                                                       scan_dict,
                                                       encoding,
                                                       compression,
                                                       title=plate_map_dict[scan_dict['coord']])
                                elif scan_dict['ms_level'] == 2:
                                    write_ms2_spectrum(writer,
                                                       data,
                                                       scan_dict,
                                                       encoding,
                                                       compression,
                                                       title=plate_map_dict[scan_dict['coord']])
                logging.info(get_timestamp() + ':' + 'Finished writing to .mzML file ' +
                             os.path.join(outdir, output_filename) + '...')

    # Group spectra from a given TSF or TDF file by sample name based on user provided plate map.
    elif maldi_output_file == 'sample' and plate_map != '':
        # Check to make sure plate map is a valid csv file.
        if os.path.exists(plate_map) and os.path.splitext(plate_map)[1] == '.csv':
            # Parse all MALDI data.
            num_frames = data.analysis[frames_key].shape[0] + 1
            # Parse TSF data.
            if data.analysis[metadata_key]['SchemaType'] == 'TSF':
                if mode == 'raw':
                    logging.info(get_timestamp() + ':' + 'TSF file detected. Only export in profile or '
                                                         'centroid mode are supported. Defaulting to centroid '
                                                         'mode.')
                list_of_scan_dicts = parse_maldi_tsf(data,
                                                     1,
                                                     num_frames,
                                                     mode,
                                                     ms2_only,
                                                     profile_bins,
                                                     encoding)
            # Parse TDF data.
            elif data.analysis[metadata_key]['SchemaType'] == 'TDF':
                list_of_scan_dicts = parse_maldi_tdf(data,
                                                     1,
                                                     num_frames,
                                                     mode,
                                                     ms2_only,
                                                     exclude_mobility,
                                                     profile_bins,
                                                     encoding)

            # Parse plate map.
            plate_map_dict = parse_maldi_plate_map(plate_map)

            # Get coordinates for each condition replicate.
            conditions = [str(value) for key, value in plate_map_dict.items()]
            conditions = sorted(list(set(conditions)))

            dict_of_scan_lists = {}
            for i in conditions:
                dict_of_scan_lists[i] = []

            for key, value in plate_map_dict.items():
                try:
                    dict_of_scan_lists[value].append(key)
                except KeyError:
                    pass

            for key, value in dict_of_scan_lists.items():
                if key != 'nan':
                    output_filename = os.path.join(outdir, key + '.mzML')

                    writer = MzMLWriter(output_filename, close=True)

                    with writer:
                        writer.controlled_vocabularies()
                        write_mzml_metadata(data, writer, infile, mode, ms2_only, barebones_metadata)
                        with writer.run(id='run', instrument_configuration='instrument'):
                            scan_count = len(value)
                            with writer.spectrum_list(count=scan_count):
                                condition_scan_dicts = [i for i in list_of_scan_dicts if i['coord'] in value]
                                scan_count = 0
                                for scan_dict in condition_scan_dicts:
                                    if ms2_only and scan_dict['ms_level'] == 1:
                                        pass
                                    else:
                                        scan_count += 1
                                        scan_dict['scan_number'] = scan_count
                                        if scan_dict['ms_level'] == 1:
                                            write_ms1_spectrum(writer,
                                                               data,
                                                               scan_dict,
                                                               encoding,
                                                               compression,
                                                               title=key)
                                        elif scan_dict['ms_level'] == 2:
                                            write_ms2_spectrum(writer,
                                                               data,
                                                               scan_dict,
                                                               encoding,
                                                               compression,
                                                               title=key)

                    logging.info(get_timestamp() + ':' + 'Finished writing to .mzML file ' +
                                 os.path.join(outdir, outfile) + '...')


def write_maldi_ims_chunk_to_imzml(data, imzml_file, frame_start, frame_stop, mode, exclude_mobility, profile_bins,
                                   encoding):
    """
    Parse and write out a group of spectra to an imzML file from a MALDI-MS(/MS) MSI dataset using pyimzML.

    :param data: Object containing raw data information from TDF or TSF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData
    :param imzml_file: Instance of pyimzml.ImzMLWriter.ImzMLWriter for output file.
    :type imzml_file: pyimzml.ImzMLWriter.ImzMLWriter
    :param frame_start: Beginning frame number.
    :type frame_start: int
    :param frame_stop: Ending frame number (non-inclusive).
    :type frame_stop: int
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param exclude_mobility: Whether to include mobility data in the output files, defaults to None.
    :type exclude_mobility: bool
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    """
    # Parse and write TSF data.
    if isinstance(data, TimsconvertTsfData):
        list_of_scan_dicts = parse_maldi_tsf(data,
                                             frame_start,
                                             frame_stop, mode,
                                             False,
                                             profile_bins,
                                             encoding)
        for scan_dict in list_of_scan_dicts:
            imzml_file.addSpectrum(scan_dict['mz_array'],
                                   scan_dict['intensity_array'],
                                   scan_dict['coord'])
    # Parse TDF data.
    elif isinstance(data, TimsconvertTdfData):
        list_of_scan_dicts = parse_maldi_tdf(data,
                                             frame_start,
                                             frame_stop,
                                             mode,
                                             False,
                                             exclude_mobility,
                                             profile_bins,
                                             encoding)
        if mode == 'profile':
            exclude_mobility = True
        if not exclude_mobility:
            for scan_dict in list_of_scan_dicts:
                imzml_file.addSpectrum(scan_dict['mz_array'],
                                       scan_dict['intensity_array'],
                                       scan_dict['coord'],
                                       mobilities=scan_dict['mobility_array'])
        elif exclude_mobility:
            for scan_dict in list_of_scan_dicts:
                imzml_file.addSpectrum(scan_dict['mz_array'],
                                       scan_dict['intensity_array'],
                                       scan_dict['coord'])


def write_maldi_ims_imzml(data, outdir, outfile, mode, exclude_mobility, profile_bins, imzml_mode, encoding,
                          compression, chunk_size):
    """
    Parse and write out spectra to an imzML file from a MALDI-MS(/MS) MSI dataset using pyimzML.

    :param data: Object containing raw data information from TDF or TSF file.
    :type data: timsconvert.classes.TimsconvertTdfData | timsconvert.classes.TimsconvertTsfData
    :param outdir: Output directory path that was specified from the command line parameters or the original input
        file path if no output directory was specified.
    :type outdir: str
    :param outfile: Output filename that was specified from the command line parameters or the original input filename
        if no output filename was specified.
    :type outfile: str
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param exclude_mobility: Whether to include mobility data in the output files, defaults to None.
    :type exclude_mobility: bool
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param imzml_mode: Whether to export spectra in "processed" (individual m/z and intensity arrays per pixel) or
        "continuous" mode (single m/z array for the entire dataset, individual intensity arrays per pixel).
    :type imzml_mode: str
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :param compression: Compression command line parameter, either "zlib" or "none".
    :type compression: str
    :param chunk_size: Number of MS1 spectra that to be used when subsetting dataset into smaller groups to pass onto
        timsconvert.write.write_lcms_chunk_to_mzml() for memory efficiency; larger chunk_size requires more memory
        during conversion.
    :type chunk_size: int
    """
    # Set polarity for run in imzML.
    polarity = list(set(data.analysis['Frames']['Polarity'].values.tolist()))
    if len(polarity) == 1 and polarity[0] == '+':
        polarity = 'positive'
    elif len(polarity) == 1 and polarity[0] == '-':
        polarity = 'negative'
    else:
        polarity = None

    if data.analysis['GlobalMetadata']['SchemaType'] == 'TSF' and mode == 'raw':
        logging.info(get_timestamp() + ':' + 'TSF file detected. Only export in profile or centroid mode are '
                                             'supported. Defaulting to centroid mode.')

    # Set centroided status.
    if mode == 'profile':
        centroided = False
    elif mode == 'centroid' or mode == 'raw':
        centroided = True

    # Get compression type object.
    if compression == 'zlib':
        compression_object = ZlibCompression()
    elif compression == 'none':
        compression_object = NoCompression()

    if data.analysis['GlobalMetadata']['SchemaType'] == 'TSF':
        writer = ImzMLWriter(os.path.join(outdir, outfile),
                             polarity=polarity,
                             mode=imzml_mode,
                             spec_type=centroided,
                             mz_dtype=get_encoding_dtype(encoding),
                             intensity_dtype=get_encoding_dtype(encoding),
                             mz_compression=compression_object,
                             intensity_compression=compression_object,
                             include_mobility=False)
    elif data.analysis['GlobalMetadata']['SchemaType'] == 'TDF':
        if mode == 'profile':
            exclude_mobility = True
            logging.info(
                get_timestamp() + ':' + 'Export of ion mobility data is not supported for profile mode data...')
            logging.info(get_timestamp() + ':' + 'Exporting without ion mobility data...')
        if not exclude_mobility:
            writer = ImzMLWriter(os.path.join(outdir, outfile),
                                 polarity=polarity,
                                 mode=imzml_mode,
                                 spec_type=centroided,
                                 mz_dtype=get_encoding_dtype(encoding),
                                 intensity_dtype=get_encoding_dtype(encoding),
                                 mobility_dtype=get_encoding_dtype(encoding),
                                 mz_compression=compression_object,
                                 intensity_compression=compression_object,
                                 mobility_compression=compression_object,
                                 include_mobility=True)
        elif exclude_mobility:
            writer = ImzMLWriter(os.path.join(outdir, outfile),
                                 polarity=polarity,
                                 mode=imzml_mode,
                                 spec_type=centroided,
                                 mz_dtype=get_encoding_dtype(encoding),
                                 intensity_dtype=get_encoding_dtype(encoding),
                                 mz_compression=compression_object,
                                 intensity_compression=compression_object,
                                 include_mobility=False)

    logging.info(get_timestamp() + ':' + 'Writing to .imzML file ' + os.path.join(outdir, outfile) + '...')
    with writer as imzml_file:
        chunk = 0
        frames = data.analysis['Frames']['Id'].to_list()
        while chunk + chunk_size + 1 <= len(frames):
            chunk_list = []
            for i, j in zip(frames[chunk:chunk + chunk_size], frames[chunk + 1: chunk + chunk_size + 1]):
                chunk_list.append((int(i), int(j)))
            logging.info(get_timestamp() + ':' + 'Parsing and writing Frame ' + ':' + str(chunk_list[0][0]) + '...')
            for frame_start, frame_stop in chunk_list:
                write_maldi_ims_chunk_to_imzml(data,
                                               imzml_file,
                                               frame_start,
                                               frame_stop,
                                               mode,
                                               exclude_mobility,
                                               profile_bins,
                                               encoding)
            chunk += chunk_size
        else:
            chunk_list = []
            for i, j in zip(frames[chunk:-1], frames[chunk + 1:]):
                chunk_list.append((int(i), int(j)))
            chunk_list.append((j, data.analysis['Frames'].shape[0] + 1))
            logging.info(get_timestamp() + ':' + 'Parsing and writing Frame ' + ':' + str(chunk_list[0][0]) + '...')
            for frame_start, frame_stop in chunk_list:
                write_maldi_ims_chunk_to_imzml(data,
                                               imzml_file,
                                               frame_start,
                                               frame_stop,
                                               mode,
                                               exclude_mobility,
                                               profile_bins,
                                               encoding)
    logging.info(get_timestamp() + ':' + 'Finished writing to .imzML file ' + os.path.join(outdir, outfile) + '...')
