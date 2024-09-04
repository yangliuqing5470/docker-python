import os
import multiprocessing
from utils import mount


def _worker(path: str, program: str, args: list) -> None:
    # 将 mount 挂载点从共享变为私有
    mount.mount("", "/", "", mount.MS_REC | mount.MS_PRIVATE)
    # 设置进程的根目录为指定路径
    os.chroot(path)
    # 将进程当前工作目录设置为根目录
    os.chdir("/")
    # 挂载 proc 伪文件系统
    mount_point = "/proc"
    mount_device = "proc"
    mount_filesystemtype = "proc"
    mount.mount(mount_device, mount_point, mount_filesystemtype)
    # 设置 PATH 环境变量
    os.putenv("PATH", "/bin")
    # 进程替换并执行指定的程序
    os.execvp(program, args)

def namespaces(path: str, program: str, args: list):
    os.unshare(os.CLONE_NEWUTS | os.CLONE_NEWPID | os.CLONE_NEWNS | os.CLONE_NEWNET | os.CLONE_NEWIPC)
    p = multiprocessing.Process(target=_worker, args=(path, program, args))
    p.start()
    # 等待子进程结束
    p.join()
