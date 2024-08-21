#!/usr/bin/env python
'''
Examples:

- Detect pagesize:
python recovery.py --nproc=4 -v --image-file start1.img pagesize --array-size=4

- Detect RAID5 sets among multiple image files:
python recovery.py -v --image-file-pattern "start?.img" --page-range=900-1024 raidset --array-size 4 --test-all --page-size=256

- Parity check of multiple image files:
python recovery.py -v --image-file start1.img --image-file start4.img --image-file start7.img  --image-file start8.img  paritycheck --page-size=256
'''

import os
import sys
import glob
import argparse
import operator
import itertools
import functools
from collections import defaultdict
from collections.abc import Sequence
import multiprocessing as mp
import numpy as np
from tqdm import tqdm

def parse_range(rangestr):
    result = []
    try:
        for r in filter(None, rangestr.split(',')):
            if r == 'all':
                return []
            if '-' in r:
                start, end = r.split('-')
                result += list(range(int(start), int(end)+1))
            else:
                result += [int(r)]
    except ValueError:
        print('Error: page ranges must be numeric')
        sys.exit(2)
    return result
            

def read(fname, pagesize, page, numpy=True):
    with open(fname, 'rb') as f:
        f.seek(page * pagesize)
        byt = f.read(pagesize)
    if numpy:
        return np.frombuffer(byt, dtype=np.uint8)
    else:
        return byt


def write(prefix, pagesize, page, output_filename):
    data = read(prefix, pagesize, page)
    with open(output_filename, 'ab') as f:
        f.write(data)


def parity_check(data_chunks):
    '''Check that data_chunks are a correct parity set'''
    parity = functools.reduce(operator.xor, data_chunks[1:])
    return np.array_equal(data_chunks[0], parity)


def guess_set(fnames, ndisks, pagesize, pages, verbose=False, test_all=False):
    '''Guess which image files are part of a RAID5 sets, looking for matching parity data'''

    detected = defaultdict(list)
    for page in nextpage(fnames, pagesize, pages):
        for comb in itertools.combinations(fnames, ndisks):
            data = [read(fname, pagesize, page) for fname in comb]
            check = parity_check(data)
            if verbose:
                print('Trying:', comb, 'Page:', page, 'Result:', 'Match' if check else 'No match')
            if check:
                detected[comb].append(True)
                if not test_all:
                    break
            else:
                detected[comb].append(False)
    good_combs = []
    for comb in detected:
        if all(detected[comb]):
            good_combs.append(comb)
    return good_combs


def raid5_stripes(ndisks, page_index, start=0):
    '''raid5 stripe arrangment for the given page index.

    The parity stripe is marked as -1'''
    stripes = [-1] * ndisks
    offset = page_index % ndisks
    first_stripe = page_index * (ndisks -1)
    for disk in range(ndisks - 1):
       stripes[disk - offset] = disk + first_stripe + start
    return stripes


def nextpage(fnames, pagesize, pages):
    if len(pages) > 0:
        for page in pages:
            yield page
        return

    sizes = [os.path.getsize(fname) for fname in fnames]
    npages = min(sizes) // pagesize
    for page in range(npages):
        yield page

def test_parity(fnames, pagesize, pages, verbose=False):

    passed = True
    ndisks = len(fnames)
    for page in nextpage(fnames, pagesize, pages):
        stripes = np.array(raid5_stripes(ndisks, page))
        data = [read(fname, pagesize, page) for fname in fnames]
        check = parity_check(data)
        if verbose:
            print(f'Page {page}: parity check', 'passed' if check else 'FAILED')
        if not check:
            passed = False
    print(f'Parity check ', 'passed' if check else 'FAILED')


def restore(prefixes, pagesize, npages, output_filename):

    ndisks = len(prefixes)
    for page in tqdm(range(npages)):
        stripes = np.array(raid5_stripes(ndisks, page))
        data = [read(prefix, pagesize, page) for prefix in prefixes]
        if not parity_check(data):
            print(f'Parity check failed for page {page}')

        sorted_idxs = np.argsort(stripes[np.where(stripes != -1)[0]])
        for prefix in np.array(prefixes)[sorted_idxs]:
            write(prefix, pagesize, page, output_filename)

def ff(page, fname, pagesize):
    data = read(fname, pagesize, page)
    if data.sum() == 0:
        return '0'
    else:
        uniq = len(np.unique(data))
        return '1' if uniq < 80 else '0'

def guess_pagesize(fnames, array_size, pages, nproc=1):
    sizesKB = [1024, 512, 256, 128, 64]
    ndisks = array_size
    search_flags = ['1'] * (ndisks-1) + ['0']
    search_pattern = ''.join(search_flags * 2)
    for szKB in sizesKB:
        flags = []
        pagesize = szKB * 1024
        with mp.Pool(nproc) as p:
            myff = functools.partial(ff, fname=fnames[0], pagesize=pagesize)
            if len(pages) == 0:
                totlen = os.path.getsize(fnames[0]) // pagesize
            else:
                totlen = len(pages)
            flags = list(tqdm(p.imap(myff, nextpage([fnames[0]], pagesize, pages)), total=totlen, desc=f'Trying {szKB}KB'))
        allflags = ''.join(flags)

        if allflags.find(search_pattern) > 0:
            print(f'Pagesize is {szKB}KB')
            return szKB
    print('No pagesize found')
    return None
               

def find_subarray(arr, subarr):
    sz = len(subarr)
    for pos in range(len(arr) - len(subarr) + 1):
        if np.array_equal(arr[pos : pos + sz], subarr):
            return pos
    return -1


def main(args):

    if args.image_file_pattern:
        if args.image_file:
            print('Only one between --image-file-pattern and --image-file can be specified')
            sys.exit(2)
        fnames = sorted(glob.glob(args.image_file_pattern))
    elif args.image_file:
        fnames = args.image_file
    else:
        print('At least one of --image-file-pattern and --image-file must be specified')
        sys.exit(2)

    pages = parse_range(args.page_range)

    if args.subcommand == 'pagesize':
        guess_pagesize(fnames, args.array_size, pages, nproc=args.nproc)
        sys.exit(0)

    if args.subcommand == 'paritycheck':
        pagesize = args.page_size
        if len(fnames) < 3:
            print('Error: need at least 3 image files for parity check')
            sys.exit(2)
        test_parity(fnames, pagesize * 1024, pages, verbose=args.verbose)
        sys.exit(0)

    if args.subcommand == 'raidset':
        pagesize = args.page_size
        ndisks = args.array_size
        if len(fnames) < ndisks:
            print(f'Not enough image files for array-size={ndisks} (only {len(files)} given)')
        detected = guess_set(fnames, ndisks, pagesize * 1024, pages, verbose=args.verbose, test_all=args.test_all)
        if len(detected) == 0:
            print('No RAID5 set detected')
        else:
            for raidset in detected:
                print('Detected RAID5 set:', raidset)
        sys.exit(0)

    if args.subcommand == 'order':
        pagesize = args.page_size
        order = guess_order(fnames, pagesize, page, args.example_file, verbose=args.verbose)    
        print('Guess order is', order)
        sys.exit(0)

    if args.subcommand == 'restore':
        pagesize = args.page_size
        ndisks = args.array_size
        order = args.order
        if os.path.exists(args.output_filename):
            print(f'{args.output_filename} already exist, nothing done')
            sys.exit(1)
        page_len = 4096
        restore(files[order], pagesize, page_len, args.output_filename)
        sys.exit(0)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='RaidRecovery')
    parser.add_argument('--image-file', type=str, action='append', help='Image file or files to analyze')
    parser.add_argument('--image-file-pattern', type=str, default=None, help='Image filename pattern')
    parser.add_argument('--page-range', type=str, default='', help='Page range to examine')
    parser.add_argument('--nproc', type=int, default=1, help='Number of processors for multiprocessing')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    subp = parser.add_subparsers(title='subcommands',
                                 description='valid subcommands',
                                 dest='subcommand')

    parser_pagesize = subp.add_parser('pagesize', help='Guess pagesize')
    parser_pagesize.add_argument('--array-size', type=int, required=True, help='RAID array size (number of disks)')

    parser_paritycheck = subp.add_parser('paritycheck', help='Check correct parity')
    parser_paritycheck.add_argument('--page-size', type=int, required=True, help='Page size in KB')

    parser_raidset = subp.add_parser('raidset', help='Guess RAID image set')
    parser_raidset.add_argument('--array-size', type=int, required=True, help='RAID array size (number of disks)')
    parser_raidset.add_argument('--page-size', type=int, required=True, default=None, help='Page size in KB')
    parser_raidset.add_argument('--test-all', action='store_true', help='Test all possible combinations')

    parser_order = subp.add_parser('order', help='Guess RAID image set')
    parser_order.add_argument('--array-size', type=int, required=True, help='RAID array size (number of disks)')
    parser_order.add_argument('--page-size', type=int, required=True, default=None, help='Page size in KB')
    parser_order.add_argument('--example-file', type=str, default=None, help='Known example file')

    parser_restore = subp.add_parser('restore', help='Restore disk image')
    parser_restore.add_argument('--page-size', type=int, required=True, default=None, help='Page size in KB')
    parser_restore.add_argument('--order', type=int, action='append', required=True, help='Ordering of input image files')
    parser_restore.add_argument('--output-filename', type=str, required=True, help='Output filename')

    args = parser.parse_args(sys.argv[1:])
    main(args)
