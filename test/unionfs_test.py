import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import unionfs


def run():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images", "busybox")
    program = "/bin/sh"
    args = ["/bin/sh"]
    unionfs.unionfs(path, program, args)


if __name__ == "__main__":
    run()
