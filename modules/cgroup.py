import os
import multiprocessing
import uuid
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
    os.putenv("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    # 进程替换并执行指定的程序
    os.execvp(program, args)


def setcgroup(pid: int, resources_limit: dict) -> str:
    """cgroup v2"""
    cgroup_root_path = "/sys/fs/cgroup/system.slice"
    current_cgroup_path = os.path.join(cgroup_root_path, "{0}-{1}".format("mydocker", uuid.uuid1().hex))
    os.makedirs(current_cgroup_path)
    with open(os.path.join(current_cgroup_path, "cgroup.procs"), "w") as fp:
        fp.write(str(pid))
    if "cpus" in resources_limit:
        with open(os.path.join(current_cgroup_path, "cpu.max"), "w") as fp:
            fp.write("{0} {1}".format(int(100000*resources_limit["cpus"]), 100000))
    if "memory" in resources_limit:
        with open(os.path.join(current_cgroup_path, "memory.max"), "w") as fp:
            fp.write(str(resources_limit["memory"] * 1024 * 1024))
        # 不使用交换内存
        with open(os.path.join(current_cgroup_path, "memory.swap.max"), "w") as fp:
            fp.write(str(0))

    return current_cgroup_path

def clearcgroup(path: str) -> None:
    if not path:
        return
    os.rmdir(path)


def cgroup(path: str, program: str, args: list):
    os.unshare(os.CLONE_NEWUTS | os.CLONE_NEWPID | os.CLONE_NEWNS | os.CLONE_NEWNET | os.CLONE_NEWIPC)
    p = multiprocessing.Process(target=_worker, args=(path, program, args))
    p.start()
    # 将子进程pid加入cgroup，并设置资源限制
    cgroup_path = ""
    if p.pid:
        resources_limit = {
            "cpus": 0.2,
            "memory": 100
        }
        cgroup_path = setcgroup(p.pid, resources_limit)
    # 等待子进程结束
    p.join()
    # 清理 cgroup 资源
    clearcgroup(cgroup_path)
