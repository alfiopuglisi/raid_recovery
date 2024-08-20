
import itertools
import functools
import operator
import numpy as np

def read_data(prefix, page_size, page):
    f = open('end'+prefix+'.img', 'rb')
    f.seek(page * page_size)
    byt = f.read(page_size)
    return np.frombuffer(byt, dtype=np.uint8)

def guess(prefixes, raid5_size, page_size, page):
    for comb in itertools.combinations(prefixes, raid5_size):
        print(comb)
        data = [read_data(prefix, page_size, page) for prefix in comb]
        parity = functools.reduce(operator.xor, data[1:])
        check = np.array_equal(data[0], parity)

        #import code
        #code.interact(local=dict(globals(), **locals()))

        if check:
           print('Match')

def main():
    page_size = 64 * 1024
    prefixes = '1 2 3 4 5 6 7 8'.split()
    raid5_size = 4
    page = 16083
    guess(prefixes, raid5_size, page_size, page)


if __name__ == '__main__':
    main()
