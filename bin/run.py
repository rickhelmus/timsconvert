import logging
import copy
from timsconvert import *


def run_tims_converter(args):
    # Load in input data.
    logging.info(get_timestamp() + ':' + 'Loading input data...')
    if not args['input'].endswith('.d'):
        input_files = dot_d_detection(args['input'])
    elif args['input'].endswith('.d'):
        input_files = [args['input']]

    # Convert each sample
    for infile in input_files:
        # Reset args.
        run_args = copy.deepcopy(args)

        # Set input file.
        run_args['infile'] = infile
        # Set output directory to default if not specified.
        if run_args['outdir'] == '':
            run_args['outdir'] = os.path.split(infile)[0]
        # Make output filename the default filename if not specified.
        if run_args['outfile'] == '':
            run_args['outfile'] = os.path.splitext(os.path.split(infile)[-1])[0] + '.mzML'

        logging.info(get_timestamp() + ':' + 'Reading file: ' + infile)
        data = bruker_to_df(infile)
        logging.info(get_timestamp() + ':' + 'Writing to file: ' + os.path.join(run_args['outdir'],
                                                                                run_args['outfile']))
        # Log arguments.
        for key, value in run_args.items():
            logging.info(get_timestamp() + ':' + str(key) + ': ' + str(value))
        write_mzml(data, run_args)
        run_args.clear()


if __name__ == '__main__':
    # Parse arguments.
    arguments = get_args()
    # Hardcode centroid to True. Current code does not support profile
    arguments['centroid'] = True

    # Check arguments.
    args_check(arguments)
    arguments['version'] = '0.0.1'

    # Initialize logger.
    logname = 'log_' + get_timestamp() + '.log'
    if arguments['outdir'] == '':
        if os.path.isdir(arguments['input']):
            logfile = os.path.join(arguments['input'], logname)
        else:
            logfile = os.path.split(arguments['input'])[0]
            logfile = os.path.join(logfile, logname)
    else:
        logfile = os.path.join(arguments['outdir'], logname)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(filename=logfile, level=logging.INFO)
    if arguments['verbose']:
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    logger = logging.getLogger(__name__)

    # Run.
    run_tims_converter(arguments)
