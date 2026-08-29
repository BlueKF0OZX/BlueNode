import time

from allstar_status import check_changes
from intelligence import build_intelligence


while True:

    try:

        check_changes()
        build_intelligence()

    except Exception as e:

        print(f"NodeSmart monitor error: {e}")


    time.sleep(5)
