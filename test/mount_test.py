import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import mount


def run():
    mount_point = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dummy")
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    mount_device = "proc"
    mount_filesystem = "proc"
    mount.mount(mount_device, mount_point, mount_filesystem)


if __name__ == "__main__":
    run()
