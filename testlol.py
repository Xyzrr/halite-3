import numpy as np
from time import process_time
import random

np.set_printoptions(precision=1, suppress=True)

a = np.zeros((10, 10))
for i in range(10):
    for j in range(10):
        a[i, j] = i*10 + j


def ship_surroundings(x, y, radius=15):
    return a.take(range(y - radius, y + radius + 1), axis=0, mode='wrap').take(range(x - radius, x + radius + 1), axis=1, mode='wrap')

def build_weight_matrix(radius=15):
    mat = np.zeros((2*radius + 1, 2*radius + 1))
    for x in range(-radius, radius + 1):
        for y in range(-radius, radius + 1):
            dis = np.abs(x) + np.abs(y)
            mat[y + radius, x + radius] = (.9 ** dis) / max(4*dis, 1)
    return mat

weight_matrix = build_weight_matrix()

for i in range(100):
    x = random.randint(0, 63)
    y = random.randint(0, 63)
    st = process_time()
    surroundings = ship_surroundings(x, y)
    c = weight_matrix * surroundings
    print(process_time() - st)