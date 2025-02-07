from timsconvert.constants import *
import pandas as pd
from pyTDFSDK.classes import TsfSpectrum, TdfSpectrum
from pyTDFSDK.util import get_centroid_status
from pyBaf2Sql.classes import BafSpectrum


def parse_lcms_baf(baf_data, frame_start, frame_stop, mode, ms2_only, profile_bins, encoding):
    """
    Parse group of frames from LC-MS(/MS) data from Bruker BAF files acquired in MS1 only, Auto MS/MS, MRM MS/MS, isCID
    MS/MS, or bbCID MS/MS mode in otofControl.

    :param baf_data: baf_data object containing metadata from analysis.sqlite database.
    :type baf_data: timsconvert.classes.TimsconvertBafData
    :param frame_start: Beginning frame number.
    :type frame_start: int
    :param frame_stop: Ending frame number (non-inclusive).
    :type frame_stop: int
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :return: Tuple of (list of dictionaries containing MS1 spectrum data, list of dictionaries containing MS/MS
    spectrum data).
    :rtype: tuple[list[pyBaf2Sql.classes.BafSpectrum]]
    """
    list_of_parent_scans = []
    list_of_product_scans = []
    for frame in range(frame_start, frame_stop):
        scan = BafSpectrum(baf_data, frame, mode, profile_bins, encoding)
        if scan.mz_array is not None and scan.intensity_array is not None and \
                scan.mz_array.size != 0 and scan.intensity_array.size != 0 and \
                scan.mz_array.size == scan.intensity_array.size:
            # MS1
            if scan.ms_level == 1 and not ms2_only:
                list_of_parent_scans.append(scan)
            # Auto MS/MS and MRM MS/MS
            elif scan.ms_level == 2 and not scan.ms2_no_precursor:
                list_of_product_scans.append(scan)
            # isCID MS/MS and bbCID MS/MS
            elif scan.ms_level == 2 and scan.ms2_no_precursor:
                list_of_parent_scans.append(scan)
    return list_of_parent_scans, list_of_product_scans


def parse_lcms_tsf(tsf_data, frame_start, frame_stop, mode, ms2_only, profile_bins, encoding):
    """
    Parse group of frames from LC-MS(/MS) data from Bruker TSF files acquired in Auto MS/MS mode MS1 only, Auto MS/MS,
    MRM MS/MS, or bbCID MS/MS mode in timsControl.

    :param tsf_data: tsf_data object containing metadata from analysis.tsf database.
    :type tsf_data: timsconvert.classes.TimsconvertTsfData
    :param frame_start: Beginning frame number.
    :type frame_start: int
    :param frame_stop: Ending frame number (non-inclusive).
    :type frame_stop: int
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :return: Tuple of (list of dictionaries containing MS1 spectrum data, list of dictionaries containing MS/MS
        spectrum data).
    :rtype: tuple[list[pyTDFSDK.classes.TsfSpectrum]]
    """
    list_of_parent_scans = []
    list_of_product_scans = []
    for frame in range(frame_start, frame_stop):
        scan = TsfSpectrum(tsf_data, frame, mode, profile_bins, encoding)
        if scan.mz_array is not None and scan.intensity_array is not None and \
                scan.mz_array.size != 0 and scan.intensity_array.size != 0 and \
                scan.mz_array.size == scan.intensity_array.size:
            if scan.ms_level == 1 and not ms2_only:
                list_of_parent_scans.append(scan)
            # Auto MS/MS
            elif scan.ms_level == 2 and not scan.ms2_no_precursor and scan.parent_frame is not None:
                list_of_product_scans.append(scan)
            # MRM MS/MS
            elif scan.ms_level == 2 and not scan.ms2_no_precursor and scan.parent_frame is None:
                list_of_parent_scans.append(scan)
            # bbCID MS/MS
            elif scan.ms_level == 2 and scan.ms2_no_precursor:
                list_of_parent_scans.append(scan)
    return list_of_parent_scans, list_of_product_scans


def parse_lcms_tdf(tdf_data, frame_start, frame_stop, mode, ms2_only, exclude_mobility, profile_bins, encoding):
    """
    Parse group of frames from LC-MS(/MS) data from Bruker TDF files acquired in MS1 only, ddaPASEF MS/MS, diaPASEF
    MS/MS, bbCID MS/MS, MRM MS/MS, or prmPASEF MS/MS mode in timsControl.

    :param tdf_data: tdf_data object containing metadata from analysis.tdf database.
    :type tdf_data: timsconvert.classes.TimsconvertTdfData
    :param frame_start: Beginning frame number.
    :type frame_start: int
    :param frame_stop: Ending frame number (non-inclusive).
    :type frame_stop: int
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param exclude_mobility: Whether to include mobility data in the output files, defaults to None.
    :type exclude_mobility: bool | None
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :return: Tuple of (list of dictionaries containing MS1 spectrum data, list of dictionaries containing MS/MS
        spectrum data).
    :rtype: tuple[list[pyTDFSDK.classes.TdfSpectrum]]
    """
    list_of_parent_scans = []
    list_of_product_scans = []
    exclude_mobility = get_centroid_status(mode, exclude_mobility)[1]

    # Frame start and frame stop will only be MS1 frames; MS2 frames cannot be used as frame_start and frame_stop.
    for frame in range(frame_start, frame_stop):
        # Parse MS1 frame(s).
        frames_dict = tdf_data.analysis['Frames'][tdf_data.analysis['Frames']['Id'] ==
                                                  frame].to_dict(orient='records')[0]

        if int(frames_dict['MsMsType']) in MSMS_TYPE_CATEGORY['ms1'] and not ms2_only:
            scan = TdfSpectrum(tdf_data, frame, mode, profile_bins=profile_bins, encoding=encoding,
                               exclude_mobility=exclude_mobility)
            if scan.mz_array is not None and scan.intensity_array is not None and \
                    scan.mz_array.size != 0 and scan.intensity_array.size != 0 and \
                    scan.mz_array.size == scan.intensity_array.size:
                list_of_parent_scans.append(scan)

            # This block only runs if frame_stop - frame_start > 1, meaning MS/MS scans are detected.
            if frame_stop - frame_start > 1:
                # Parse frames with ddaPASEF spectra for precursors.
                if int(frames_dict['ScanMode']) == 8 and int(frames_dict['MsMsType']) == 0:
                    precursor_dicts = tdf_data.analysis['Precursors'][tdf_data.analysis['Precursors']['Parent'] ==
                                                                      frame].to_dict(orient='records')
                    for precursor_dict in precursor_dicts:
                        scan = TdfSpectrum(tdf_data, frame, mode, precursor=precursor_dict['Id'],
                                           profile_bins=profile_bins, encoding=encoding,
                                           exclude_mobility=exclude_mobility)

                        if scan.mz_array is not None and scan.intensity_array is not None and \
                                scan.mz_array.size != 0 and scan.intensity_array.size != 0 and \
                                scan.mz_array.size == scan.intensity_array.size:
                            list_of_product_scans.append(scan)
        # Parse frames with diaPASEF spectra.
        elif int(frames_dict['ScanMode']) == 9 and int(frames_dict['MsMsType']) == 9:
            diaframemsmsinfo_dict = tdf_data.analysis['DiaFrameMsMsInfo'][tdf_data.analysis['DiaFrameMsMsInfo']['Frame'] ==
                                                                          frame].to_dict(orient='records')[0]
            diaframemsmswindows_dicts = tdf_data.analysis['DiaFrameMsMsWindows'][tdf_data.analysis['DiaFrameMsMsWindows']['WindowGroup'] ==
                                                                                 diaframemsmsinfo_dict['WindowGroup']].to_dict(orient='records')

            for diaframemsmswindows_dict in diaframemsmswindows_dicts:
                scan = TdfSpectrum(tdf_data, frame, mode, diapasef_window=diaframemsmswindows_dict,
                                   profile_bins=profile_bins, encoding=encoding, exclude_mobility=exclude_mobility)
                if scan.mz_array is not None and scan.intensity_array is not None and \
                        scan.mz_array.size != 0 and scan.intensity_array.size != 0 and \
                        scan.mz_array.size == scan.intensity_array.size:
                    list_of_parent_scans.append(scan)
        # Parse frames with bbCID, MRM, or prm-PASEF spectra.
        elif (int(frames_dict['ScanMode']) == 4 and int(frames_dict['MsMsType']) == 2) or \
                (int(frames_dict['ScanMode']) == 2 and int(frames_dict['MsMsType']) == 2) or \
                (int(frames_dict['ScanMode']) == 10 and int(frames_dict['MsMsType']) == 10):
            scan = TdfSpectrum(tdf_data, frame, mode, profile_bins=profile_bins, encoding=encoding,
                               exclude_mobility=exclude_mobility)
            if scan.mz_array is not None and scan.intensity_array is not None and \
                    scan.mz_array.size != 0 and scan.intensity_array.size != 0 and \
                    scan.mz_array.size == scan.intensity_array.size:
                list_of_parent_scans.append(scan)
    return list_of_parent_scans, list_of_product_scans


def parse_maldi_plate_map(plate_map_filename):
    """
    Parse a MALDI plate map from a CSV file without a column header or row index.

    :param plate_map_filename: Path to the MALDI plate map in CSV format.
    :type plate_map_filename: str
    :return: Dictionary containing standard MTP spot names as the key and spot label/category/condition as the value.
    :rtype: dict
    """
    plate_map = pd.read_csv(plate_map_filename, header=None)
    plate_dict = {}
    for index, row in plate_map.iterrows():
        for count, value in enumerate(row, start=1):
            plate_dict[chr(index + 65) + str(count)] = value
    return plate_dict


def parse_maldi_tsf(tsf_data, frame_start, frame_stop, mode, ms2_only, profile_bins, encoding):
    """
    Parse group of frames from MALDI-MS(/MS) data from Bruker TSF files acquired in MS1 only, MS/MS, or bbCID MS/MS
    mode in timsControl.

    :param tsf_data: tsf_data object containing metadata from analysis.tsf database.
    :type tsf_data: timsconvert.classes.TimsconvertTsfData
    :param frame_start: Beginning frame number.
    :type frame_start: int
    :param frame_stop: Ending frame number (non-inclusive).
    :type frame_stop: int
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :return: List of dictionaries containing spectrum data.
    :rtype: list[pyTDFSDK.classes.TsfSpectrum]
    """
    list_of_scans = []
    for frame in range(frame_start, frame_stop):
        scan = TsfSpectrum(tsf_data, frame, mode, profile_bins, encoding)
        if scan.mz_array is not None and scan.intensity_array is not None and \
                scan.mz_array.size != 0 and scan.intensity_array.size != 0 and \
                scan.mz_array.size == scan.intensity_array.size:
            if scan.ms_level == 1 and ms2_only:
                pass
            else:
                list_of_scans.append(scan)
    return list_of_scans


def parse_maldi_tdf(tdf_data, frame_start, frame_stop, mode, ms2_only, exclude_mobility, profile_bins, encoding):
    """
    Parse group of frames from MALDI-MS(/MS) data from Bruker TDF files acquired in MS1 only, MS/MS, or bbCID MS/MS
    mode in timsControl.

    :param tdf_data: tdf_data object containing metadata from analysis.tdf database.
    :type tdf_data: timsconvert.classes.TimsconvertTdfData
    :param frame_start: Beginning frame number.
    :type frame_start: int
    :param frame_stop: Ending frame number (non-inclusive).
    :type frame_stop: int
    :param mode: Mode command line parameter, either "profile", "centroid", or "raw".
    :type mode: str
    :param ms2_only: Whether to include MS1 data in the output files.
    :type ms2_only: bool
    :param exclude_mobility: Whether to include mobility data in the output files, defaults to None.
    :type exclude_mobility: bool | None
    :param profile_bins: Number of bins to bin spectrum to.
    :type profile_bins: int
    :param encoding: Encoding command line parameter, either "64" or "32".
    :type encoding: int
    :return: List of dictionaries containing spectrum data.
    :rtype: list[pyTDFSDK.classes.TdfSpectrum]
    """
    list_of_scans = []
    exclude_mobility = get_centroid_status(mode, exclude_mobility)[1]
    for frame in range(frame_start, frame_stop):
        scan = TdfSpectrum(tdf_data, frame, mode, profile_bins=profile_bins, encoding=encoding,
                           exclude_mobility=exclude_mobility)
        if scan.mz_array is not None and scan.intensity_array is not None and \
                scan.mz_array.size != 0 and scan.intensity_array.size != 0 and \
                scan.mz_array.size == scan.intensity_array.size:
            if scan.ms_level == 1 and ms2_only:
                pass
            else:
                list_of_scans.append(scan)
    return list_of_scans
