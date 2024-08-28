import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import namespaces


def run():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "root")
    program = "/bin/sh"
    args = ["/bin/sh"]
    namespaces.namespaces(path, program, args)


if __name__ == "__main__":
    run()
