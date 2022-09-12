import os


def add_source_args(parser):
    parser.add_argument('--in', dest='path_in', type=str, required=False,
                        help='Path to a single SWF file')
    parser.add_argument('--list', dest='list_in', type=str, required=False,
                        help='Path to a file with SWF file paths list, separated by newline')
    parser.add_argument('--dir', dest='dir_in', type=str, required=False,
                        help='Path to a directory with SWF files')


def get_source_paths(args):
    if args.path_in is not None:
        return [args.path_in]
    elif args.list_in is not None:
        return _read_list_file(args.list_in)
    elif args.dir_in is not None:
        return _list_dir(args.dir_in)
    raise RuntimeError('No input files defined')


def _read_list_file(path):
    with open(path, 'rt') as f:
        for line in f:
            line = line.strip()
            if line:
                yield line


def _list_dir(path):
    for filename in os.listdir(path):
        yield os.path.join(path, filename)
