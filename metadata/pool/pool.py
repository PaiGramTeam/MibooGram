from metadata.pool.pool_1 import POOL_1
from metadata.pool.pool_2 import POOL_2
from metadata.pool.pool_3 import POOL_3
from metadata.pool.pool_4 import POOL_4


def get_pool_by_id(pool_type):
    if pool_type == 1:
        return POOL_1
    if pool_type == 2:
        return POOL_2
    if pool_type == 3:
        return POOL_3
    if pool_type == 4:
        return POOL_4
    return None
