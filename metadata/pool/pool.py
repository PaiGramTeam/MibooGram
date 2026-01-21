from metadata.pool.pool_1 import POOL_1
from metadata.pool.pool_2 import POOL_2
from metadata.pool.pool_3 import POOL_3
from metadata.pool.pool_5 import POOL_5
from metadata.pool.pool_102 import POOL_102
from metadata.pool.pool_103 import POOL_103


def get_pool_by_id(pool_type):
    if pool_type == 1:
        return POOL_1
    if pool_type == 2:
        return POOL_2
    if pool_type == 3:
        return POOL_3
    if pool_type == 5:
        return POOL_5
    if pool_type == 102:
        return POOL_102
    if pool_type == 103:
        return POOL_103
    return None
