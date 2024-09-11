import os
import random
import multiprocessing
import shutil
import subprocess
import uuid
from utils import mount


def _worker(path: str, program: str, args: list, pipe_conn) -> None:
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
    # 设置容器内部的网络
    if pipe_conn.recv() == "container network init":
        setcontainernet()
    # 进程替换并执行指定的程序
    os.execvp(program, args)

def _run_command(command: list):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            return True
        else:
            if ["ip", "link", "show", "my-br0"] != command:
                print("Error {0} with command {1}".format(result.stderr, command))
            return False
    except Exception as e:
        print(f"An error occurred: {0} with command {1}".format(e, command))
        return False


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


def clearnet():
    _run_command(["ip", "link", "delete", "my-br0"])
    _run_command(["iptables", "-t", "nat", "-D", "POSTROUTING", "1"])
    _run_command(["iptables", "-D", "FORWARD", "1"])
    _run_command(["iptables", "-D", "FORWARD", "1"])


def sethostnet(pid: int):
    # 检查网桥 my-br0 是否存在，不存在创建网桥分配 172.16.0.1/16 地址
    if not _run_command(["ip", "link", "show", "my-br0"]):
        if not _run_command(["ip", "link", "add", "name", "my-br0", "type", "bridge"]):
            return
        if not _run_command(["ip", "addr", "add", "172.16.0.1/16", "dev", "my-br0"]):
            return
        if not _run_command(["ip", "link", "set", "my-br0", "up"]):
            return
    # 创建 veth 一对网络接口设备，一端在宿主机网络，另一端在容器网络
    if not _run_command(["ip", "link", "add", "veth-host-{0}".format(pid), "type", "veth", "peer", "name", "veth-container"]):
        return
    if not _run_command(["ip", "link", "set", "veth-container", "netns", "{0}".format(pid)]):
        return
    if not _run_command(["ip", "link", "set", "veth-host-{0}".format(pid), "up"]):
        return
    if not _run_command(["ip", "link", "set", "veth-host-{0}".format(pid), "master", "my-br0"]):
        return
    # 设置 iptables 路由规则支持 NAT 地址转换
    if not _run_command(["iptables", "-I", "FORWARD", "1", "-i", "my-br0", "!", "-o", "my-br0", "-j", "ACCEPT"]):
        return
    if not _run_command(["iptables", "-I", "FORWARD", "1", "-o", "my-br0", "-m", "conntrack", "--ctstate", "RELATED,ESTABLISHED", "-j", "ACCEPT"]):
        return
    if not _run_command(["iptables", "-t", "nat", "-I", "POSTROUTING", "1", "-s", "172.16.0.0/16", "!", "-o", "my-br0", "-j", "MASQUERADE"]):
        return
    print("Host network set completed with inface veth-host-{0}".format(pid))

def setcontainernet():
    num = random.randint(2, 254)
    # 开启 127.0.0.1 接口
    if not _run_command(["ip", "link", "set", "lo", "up"]):
        return
    # 开启容器网络接口并分配 172.16.0.2/16 地址
    if not _run_command(["ip", "addr", "add", "172.16.0.{0}/16".format(num), "dev", "veth-container"]):
        return
    if not _run_command(["ip", "link", "set", "veth-container", "up"]):
        return
    # 容器内部添加默认路由
    if not _run_command(["ip", "route", "add", "default", "via", "172.16.0.1"]):
        return
    print("Container netwroking set completed with inface veth-container: 172.16.0.{0}/16".format(num))


def sethostnet_task(child_conn_task, parent_conn):
    # 等待容器进程启动
    pid = child_conn_task.recv()
    sethostnet(int(pid))
    # 通知容器进程开始执行网络初始化
    parent_conn.send("container network init")
    # 等待清理网络资源
    child_conn_task.recv()
    clearnet()
    # 清理容器运行时目录
    path = child_conn_task.recv()
    _run_command(["umount", path])
    os.rmdir(path)


def _unionfs(path: str, program: str, args: list):
    # 在调用 unshare 隔离 namespaces 前启动一个进程用来执行宿主机网络初始化操作
    parent_conn_task, child_conn_task = multiprocessing.Pipe()
    parent_conn, child_conn = multiprocessing.Pipe()

    p_task = multiprocessing.Process(target=sethostnet_task, args=(child_conn_task, parent_conn))
    p_task.start()

    os.unshare(os.CLONE_NEWUTS | os.CLONE_NEWPID | os.CLONE_NEWNS | os.CLONE_NEWNET | os.CLONE_NEWIPC)
    p = multiprocessing.Process(target=_worker, args=(path, program, args, child_conn))
    p.start()

    cgroup_path = ""
    if p.pid:
        # 将子进程pid加入cgroup，并设置资源限制
        resources_limit = {
            "cpus": 0.2,
            "memory": 100
        }
        cgroup_path = setcgroup(p.pid, resources_limit)
        # 通知设置宿主机网络
        parent_conn_task.send(p.pid)
    # 等待子进程结束
    p.join()
    # 清理 cgroup 资源
    clearcgroup(cgroup_path)
    # 通知宿主机清理网络资源
    parent_conn_task.send("clear network")
    # 清理容器运行时目录
    parent_conn_task.send(path)


def unionfs(images_path: str, program: str, args: list):
    container_id = uuid.uuid1().hex
    containers_root_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "containers")
    if not os.path.exists(containers_root_path):
        os.makedirs(containers_root_path)
    runtime_root_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime")
    if not os.path.exists(runtime_root_path):
        os.makedirs(runtime_root_path)
    # 容器目录
    container_path = os.path.join(containers_root_path, container_id)
    os.makedirs(container_path)
    # 运行时目录
    runtime_path = os.path.join(runtime_root_path, container_id)
    os.makedirs(runtime_path)
    runtime_tmpwork = os.path.join(runtime_root_path, "tmpwork")
    if os.path.exists(runtime_tmpwork):
        os.rmdir(runtime_tmpwork)
    os.makedirs(runtime_tmpwork)
    # 执行 unionfs 文件系统挂载
    options = "lowerdir={0},upperdir={1},workdir={2}".format(images_path, container_path, runtime_tmpwork)
    mount.mount("overlay", runtime_path, "overlay", options=options)
    # 拷贝 resolv.conf 用于域名解析
    if not os.path.exists(os.path.join(container_path, "etc")):
        os.makedirs(os.path.join(container_path, "etc"))
    shutil.copy2("/etc/resolv.conf", os.path.join(container_path, "etc", "resolv.conf"))
    _unionfs(runtime_path, program, args)
