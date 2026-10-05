"""Own the CLI process group, including children left behind after CLI exit."""

from __future__ import annotations

import os
import signal
import subprocess
import time


class _WindowsJob:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w

        class BasicLimits(c.Structure):
            _fields_ = [
                ("user_time", c.c_int64),
                ("job_time", c.c_int64),
                ("flags", w.DWORD),
                ("min_working_set", c.c_size_t),
                ("max_working_set", c.c_size_t),
                ("active_limit", w.DWORD),
                ("affinity", c.c_size_t),
                ("priority", w.DWORD),
                ("scheduling", w.DWORD),
            ]

        class ExtendedLimits(c.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io", c.c_uint64 * 6),
                ("process_memory", c.c_size_t),
                ("job_memory", c.c_size_t),
                ("peak_process_memory", c.c_size_t),
                ("peak_job_memory", c.c_size_t),
            ]

        self.c = c
        self.api = c.WinDLL("kernel32", use_last_error=True)
        for name, args, result in (
            ("CreateJobObjectW", [w.LPVOID, w.LPCWSTR], w.HANDLE),
            ("SetInformationJobObject", [w.HANDLE, c.c_int, w.LPVOID, w.DWORD], w.BOOL),
            (
                "QueryInformationJobObject",
                [w.HANDLE, c.c_int, w.LPVOID, w.DWORD, w.LPVOID],
                w.BOOL,
            ),
            ("AssignProcessToJobObject", [w.HANDLE, w.HANDLE], w.BOOL),
            ("TerminateJobObject", [w.HANDLE, w.UINT], w.BOOL),
            ("CloseHandle", [w.HANDLE], w.BOOL),
        ):
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise c.WinError(c.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, c.byref(limits), c.sizeof(limits)
        ):
            error = c.WinError(c.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise self.c.WinError(self.c.get_last_error())

    def finish(self, timeout=5):
        c = self.c
        # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four LARGE_INTEGERs,
        # followed by PageFaultCount, TotalProcesses, ActiveProcesses, Terminated.
        info = (c.c_uint64 * 6)()
        if not self.api.TerminateJobObject(self.handle, 1):
            raise c.WinError(c.get_last_error())
        deadline = time.monotonic() + timeout
        while True:
            if not self.api.QueryInformationJobObject(
                self.handle, 1, c.byref(info), c.sizeof(info), None
            ):
                raise c.WinError(c.get_last_error())
            active = c.cast(c.byref(info), c.POINTER(c.c_uint32))[10]
            if active == 0:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("CLI process group did not exit")
            time.sleep(0.05)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class OwnedProcess:
    def __init__(self):
        self.process = None
        self.job = None

    def start(self, command, **kwargs):
        try:
            if os.name == "nt":
                import psutil

                self.job = _WindowsJob()
                # Assign before executing any code so fast-spawned helpers are
                # owned too. No breakaway flag: children inherit this job.
                self.process = subprocess.Popen(
                    command, creationflags=subprocess.CREATE_NO_WINDOW | 0x4, **kwargs
                )
                self.job.assign(self.process)
                psutil.Process(self.process.pid).resume()
            else:
                self.process = subprocess.Popen(
                    command, start_new_session=True, **kwargs
                )
            return self.process
        except Exception:
            if self.process is not None:
                self.process.kill()
                self.process.wait(timeout=5)
            if self.job:
                self.job.close()
            raise

    def cleanup(self):
        try:
            if self.job and self.job.handle:
                self.job.finish()
            elif self.process and not self.job:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(self.process.pid, sig)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
                    time.sleep(0.05)
                try:
                    self.process.kill()
                except Exception:
                    pass
        finally:
            if self.job:
                self.job.close()
            if self.process:
                try:
                    if self.process.stdin and not self.process.stdin.closed:
                        self.process.stdin.close()
                finally:
                    try:
                        self.process.wait(timeout=5)
                    except Exception:
                        pass
