import ctypes
import ctypes.util
import os


libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
libc.mount.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p)

MS_PRIVATE = 1 << 18
MS_REC = 1 << 14


def mount(source, target, fs, mountflags=0, options=''):
    ret = libc.mount(source.encode(), target.encode(), fs.encode(), mountflags, options.encode())
    if ret < 0:
      errno = ctypes.get_errno()
      raise OSError(errno, f"Error mounting {source} ({fs}) on {target} with options '{options}': {os.strerror(errno)}")
