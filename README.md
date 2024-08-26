
# RAID5 data recovery tool

Command line utility to recover RAID5 data from disk images, even
when the RAID superblock has been deleted and thus it is not possible
to identify which disk image belongs to which RAID array, and in whcih order.

Implements the following actions, in approximate logical order of recovery:

- page size detection
- disk image identification
- parity check
- disk image ordering in array
- data reconstruction

## A bit of history

Once upon a time, eight disks lived inside a server, configured as two RAID5 arrays
of four disks each, with an offline backup. All disks were almost full, and at 8TB per disk,
it meant some 48TB of actual data. Through a series of stunningly careless mistakes
the backup was incomplete, the two RAID5 virtual disks were deleted (zeroing out
the RAID5 superblock) and all disks physically removed from the server without
taking note of their position.

The final result was 48TB of non-backed up data and parity checksums 
distributed among eight 8TB disks in a rather unknown pattern. Someone had
enough foresight to make a low-level copy of each disk with the Unix "dd" utility,
but since things were still too boring, it came out that
the USB adapters used to generate disk image files were unreliable enough that
disk copy was interrupted and restarted several times, ending up with each image file
split into several multi-TB pieces.

This recovery tool and the subsequent NBD plugin for RAID virtual disks are the
result of the frantic data recovering efforts.


## Dependencies

- `numpy`
- `tqdm`

Install them with pip or whatever:

`pip install numpy tqdm`

## Syntax

```
python recovery.py [common options] <action> [action options]
```


## Common options

- `--nproc=N`:  use N processors with Python multiprocessing, where applicable. Default 1 processor.
- `--image-file=file.img`: work on image file "file.img"
- `--image-file-pattern="file?.img"`: work on the list of image files matching the bash pattern. Use double quotes to prevent the shell from interpreting it directly.
- `--page-range=0,2-10-200,30`: comma-separated list of page ranges to examine (python ranges, excludes the last element). Default is to examine the whole file.
- `-v, --verbose`: verbose output
- `-h, --help`: show detailed help

## Commands

- `pagesize`: page size detection
- `raidset`: disk image identification
- `paritycheck`: parity check
- `order`: disk image ordering in array
- `restore`: RAID5 reconstruction


### Page size detection

Parameters:
- `--array-size`: RAID array size (number of disks). Mandatory.

RAID page sizes usually range from 64KB to 1024MB, depending on how the array was defined.
This detection algorithm uses a heuristic based on ASCII files statistics: an ASCII file
will typically use only ~70 separate characters, while the parity calculation will fill
almost the whole 7-bit space. Therefore there will be an alternating pattern of N pages
with a reduced character count, and 1 page with an increased one.
In order for this algorithm to work, a very long ASCII file needs to be present on disk,
ideally a few MB at least. In addition to English text, Many other kind of text files
can work: csv, logs, html. Only a single disk image needs to be examined.

This algorithm can be quite slow so it supports the --nproc=N option for parallel
processing. In addition it is possible to truncate the image file to a few GB since
there is no need for the whole array to be examined, just a portion containing
the right kind of file.

Since this algorithm uses an heuristic, results are not guaranteed. In the worst case,
image files can be examined with an hex editor to look for patterns.

If the page size is known, this step can be skipped.



### Disk image identification

If available image files used to belong to multiple RAID5 arrays, it is necessary
to identify which images belonged to a specific array. This algorithm tries all
possible image files combinations until it finds a group of files matching the RAID5
parity calculation. All matches will be reported, thus it is possible that multiple
RAID arrays will be identified

The output will be a list of image files belonging to a single RAID5 array.
The exact order will still be unknown, since the parity algorithm is symmetric and
cannot be used to identify which image files contains the data and which one
is the additional parity data.

It is possible to run this algorithm on a small subset of the data,
for example just a few GBs, using the --page-range option. As long as the selected
subset contains actual data and not just zeroes, identification should be reliable.
If results are ambiguous, just increase the page range and try again.

If it is known which image files belonged to a certain RAID5 array, this step
can be skipped.

Parameters:
- `--array-size`: RAID array size (number of disks). Mandatory.
- `--page-size`: Page size in KB. Mandatory.
- `--test-all`: Test all possible combinations instead of stopping at the first one. Recommended.

### Parity check

As a data integrity check, a simple parity check can be run on the whole length
of image files belonging to a single RAID5 array. The output is a simple pass/fail result.

Parameters:
- `--page-size`: Page size in KB. Mandatory.


### RAID5 sequence detection

Once the image files belonging to a single RAID5 array have been identified,
it is necessary to detect the correct order for array reconstruction.
A heuristic algorithm similar to the one used for page size detection will
detect which one of the image files is the parity one (for each RAID5 page),
and will output the correct image file ordering. The heuristic uses the
same ASCII file patterns described in the page size detection step.

Since this algorithm uses an heuristic, results are not guaranteed. In the worst case,
image files can be examined with an hex editor to look for patterns.

Parameters:
- `--page-size`: Page size in KB. Mandatory.

### RAID5 data recontruction

Once both page size and image file order is known, all data can be restored.
This step will read the image files, extract data from the RAID pages in the
correct sequence, and produce a single output file with the virtual drive content.

The resulting file can be examined with fdisk and then mounted as a loopback device
as if it was an image file of a single disk.

Parameters:
- `--page-size`: Page size in KB. Mandatory.
- `--output-filename`: Output filename. Mandatory


# RAID5 virtual disk

As an alternative to the data reconstruction above (which might need dozens of TB
of free disk space, in addition to the space already taken by the raw disk images), 
`nbd_raid5.py` is Python [nbdkit](https://www.libguestfs.org/nbdkit.1.html) plugin to export a virtual drive starting from disk images once part of a RAID5 array. The RAID superblock does not need to be present. The disk image ordering and RAID page size must be known, in case they can be found with the RAID5 recovery tools described above.

Each disk can be split into multiple image files, i.e. to keep the file size manageable or because the imaging tool can be unreliable when multiple TBs are involved. A geometry file describes how image files are arranged:


```
$ cat geometry.txt 

# id  RAID_idx   file         startMB   endMB
0        0       disk4a.img   0         4813759
1        0       disk4b.img   4813759   7630885.3359375
2        1       disk8a.img   0         7630885.3359375
3        2       disk1a.img   0         2549811
4        2       disk1b.img   2549811   7630885.3359375
5        3       disk7a.img   0         1651088
6        3       disk7b.img   1651088   7630885.3359375
```

Columns are:
- id: unique ID for each file. Any format.
- RAID_idx: RAID disk index of this image file, numeric starting from zero.
- file:  filename of this image file
- startMB:  image file starting point in MB
- endMB: image file end point in MB

All empty lines and lines starting with `#` are ignored.

startMB and endMB can be fractional, but should be a multiple of the RAID page size, typically 64K or 256K.
In this example, "disk4a.img" is an image file of the first RAID disk, contaning the first 4813759 MB of the disk. The rest of the data from the first RAID disk is in file "disk4b.img". The assignment of "disk4" to the first RAID set was done with the RAID5 recovery tools described above and manually confirmed with an hex editor.


## Install nbd-server and nbd-client

Hopefully you have them in your distribution archives. On Ubuntu:

`sudo apt install nbd-server nbd-client`

## Install nbdkit

In my case nbdkit was not available on the apt archives.

1. Clone nbdkit from `https://gitlab.com/nbdkit/nbdkit.git`

2. Python plugin uses Python3. On older systems, make sure that the default Python is verson 3. In case, you can try to set the PYTHON environment variable to the python executable, e.g. "export PYTHON=/usr/bin/python3"

3. Make sure that you have the Python development packages installed

4. Build and install nbdkit:

```
autoreconf -i
./configure
make
sudo make install
```

You might have to play with ./configure settings, for example to disable curl or zstd if some development libraries are missing from your system.


## Start the server

The first server parameter must be `script=<python script path>`. The -v and -f flags force the server
to remain in foreground and print debug information. Other parameters are passed to the Python script.

```
nbdkit -f -v python script=./nbd_raid5.py geometryfile=geometry.txt pagesizeKB=256
```

## Start the client (as root):

On the same (localhost) or a different computer:

```
nbd-client localhost /dev/nbd0
```

## Verify that fdisk works:

```
fdisk -l /dev/nbd0
```

Should show a partition table.

## Mount partitions

Inspect with an hex editor looking for the EXT4 magic number: 0x53EF (already written in little endian). This magic number is at address 0x438 after the partition start. In my case I found it at 0x100438 therefore the partition was starting at 0x100000 (one megabyte)
Mount the partition using the found position as the offset:

```
mount -o offset=1048576,ro /dev/nbd0 /mnt
```

You should now find the virtual file system in /mnt

