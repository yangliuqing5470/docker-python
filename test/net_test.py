import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import net


def run():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images", "ubuntu")
    program = "/bin/sh"
    args = ["/bin/sh"]
    net.net(path, program, args)


if __name__ == "__main__":
    run()
