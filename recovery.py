
import itertools
import functools
import operator

def read_data(prefix, page_size, page):
    f = open(prefix+'.img', 'rb')
    f.seek(page * page_size)
    return f.read(page_size)

def guess(prefixes, raid5_size, page_size, page):
    for comb in itertools.combinations(prefixes, raid5_size):
        data = [read_data(prefix, page_size, page) for prefix in comb]
        parity = functools.reduce(data[1:], operator.xor)
        check = (data[0] == parity)
        if check:
            return comb

def main():
    page_size = 64 * 1024
    prefixes = '0 1 2 3 4 5 6 7'.split()
    raid5_size = 4
    page = 1000000
    guess(prefixes, raid5_size, page_size, page)

