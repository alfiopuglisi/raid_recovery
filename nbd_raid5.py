
# Run it from the build directory like this:
#
# nbdkit -f -v python script=./nbd_raid5.py geometryfile=geometry.txt pagesizeKB=256
#
# The -f -v arguments are optional.  They cause the server to stay in
# the foreground and print debugging, which is useful when testing.



import os
import numpy as np
from collections import namedtuple


DiskGeometry = namedtuple('DiskGeometry', 'id raid_index fname startKB endKB')

builtin_open= open
geometry_file = None
pagesizeKB = -1

API_VERSION = 2


def config(key, value):
    global geometry_file
    global pagesizeKB

    if key == 'geometryfile':
        geometry_file = value
    elif key == 'pagesizeKB':
        pagesizeKB = int(value)
    else:
        print("ignored parameter %s=%s" % (key, value))


def open(readonly):
    fd = {}
    geometry = read_geometry(geometry_file)
    for image in geometry:
        fd[image.id] = builtin_open(image.fname, 'rb')
    return (geometry, fd)


def get_size(h):
    geometry, fd = h

    sizesKB = [(image.endKB - image.startKB) for image in geometry]
    ndisks = len(set([image.raid_index for image in geometry]))
    return sum(sizesKB) * 1024 * (ndisks-1) // ndisks
      

def pread(h, buf, offset, flags):
    geometry, fd = h

    ndisks = len(set([image.raid_index for image in geometry]))
    raidpagesize = pagesizeKB * 1024 * (ndisks - 1)
    start_page = offset // raidpagesize
    end_page = (offset + len(buf)) // raidpagesize + 1 
    mod_page = offset % raidpagesize
    pos = 0
    for page in range(start_page, end_page):
        stripes = raid5_stripes(ndisks, page)  # RAID stripes ordering in given page
        sorted_idxs = np.argsort(stripes)[1:]   # sorted RAID disks to read, excluding parity

        pageKB = page * pagesizeKB  # Page KB address on the single disk

        # Read stripes in order
        mybuf = []
        for raid_idx in sorted_idxs:
            for image in geometry:
                if image.raid_index == raid_idx and image.startKB <= pageKB and image.endKB > pageKB:
                    # Image files are at multiples of page size,
                    # so there is no need to split reads
                    myoffset = pageKB - image.startKB
                    fd[image.id].seek(myoffset * 1024)
                    mybuf.append(fd[image.id].read(pagesizeKB * 1024))

        # Assemble full RAID page and cut start and end if needed
        mybuf = b''.join(mybuf)
        mybuf = mybuf[mod_page:]

        if pos + len(mybuf) > len(buf):
            mylen = len(buf) - pos
        else:
            mylen = len(mybuf)
        if mylen == 0:
            break
        buf[pos : pos + mylen] = mybuf[:mylen]
        pos += mylen
        mod_page = 0   # No need to cut the start position after the first page


def raid5_stripes(ndisks, page_index, start=0):
    '''raid5 stripe arrangment for the given page index.
    The parity stripe is marked as -1'''
    stripes = [-1] * ndisks
    offset = page_index % ndisks
    first_stripe = page_index * (ndisks -1)
    for disk in range(ndisks - 1):
       stripes[disk - offset] = disk + first_stripe + start
    return stripes

def read_geometry(fname):
    images = []
    lines = builtin_open(fname).readlines()
    for line in lines:
        line = line.strip()
        if line == '' or line[0] == '#':
            continue
        id, raid_idx, fname, start, end = line.split()
        images.append(DiskGeometry(id, int(raid_idx), fname, int(float(start)*1024), int(float(end)*1024)))
    return images

