using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

// Windows Job Object: 이 프로세스를 담은 Job의 핸들이 닫히면(= 이 프로세스가 어떻게 끝나든)
// Job 안의 모든 프로세스(자식·손자 포함)가 OS에 의해 종료된다. cmd 창만 닫으면
// 그 아래 node/python이 남아 메모리를 잡고 있던 문제를 막는다.
static class ProcessJob
{
    const int JobObjectExtendedLimitInformation = 9;
    const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;

    [StructLayout(LayoutKind.Sequential)]
    struct BasicLimits
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct IoCounters
    {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct ExtendedLimits
    {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr CreateJobObject(IntPtr attributes, string name);

    [DllImport("kernel32.dll")]
    static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint size);

    [DllImport("kernel32.dll")]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    // 프로세스가 끝날 때까지 핸들을 닫지 않는다 — 닫히는 순간이 곧 "모두 종료"다.
    static IntPtr jobHandle = IntPtr.Zero;

    public static bool KillChildrenWhenThisProcessEnds()
    {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) return false;

        var limits = new ExtendedLimits();
        limits.Basic.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        int size = Marshal.SizeOf(typeof(ExtendedLimits));
        IntPtr buffer = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(limits, buffer, false);
            if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, buffer, (uint)size)) return false;
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }

        if (!AssignProcessToJobObject(job, Process.GetCurrentProcess().Handle)) return false;
        jobHandle = job;
        return true;
    }
}

class Launcher
{
    static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string backendDir = Path.Combine(root, "backend");
        string frontendDir = Path.Combine(root, "frontend");

        if (!Directory.Exists(backendDir) || !Directory.Exists(frontendDir))
        {
            Console.WriteLine("backend/ or frontend/ folder not found next to this exe.");
            Console.WriteLine("Put this exe in the project root (same folder as backend/ and frontend/).");
            Pause();
            return;
        }

        string python = FindPython(backendDir);
        if (python == null)
        {
            Console.WriteLine("Could not find a Python interpreter.");
            Console.WriteLine("Set one up first: cd backend && python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt");
            Console.WriteLine("Or make sure 'py' or 'python' is on PATH.");
            Pause();
            return;
        }

        // 이 런처가 끝나면(창을 닫거나 키를 눌러도) 아래에서 띄우는 서버 프로세스 트리 전체가 함께 끝난다.
        // 자식을 띄우기 전에 걸어야 그 자식들이 같은 Job에 자동으로 들어온다.
        bool stopsWithLauncher = ProcessJob.KillChildrenWhenThisProcessEnds();

        StartInCmdWindow("Backend (uvicorn :8000)",
            "\"" + python + "\" -m uvicorn app.main:app --host 127.0.0.1 --port 8000", backendDir);

        StartInCmdWindow("Frontend (next dev :3000)", "npm run dev", frontendDir);

        Console.WriteLine("Started backend and frontend in separate windows.");
        Console.WriteLine("Opening the browser in a few seconds...");
        System.Threading.Thread.Sleep(4000);
        Process.Start(new ProcessStartInfo("http://localhost:3000") { UseShellExecute = true });

        if (stopsWithLauncher)
        {
            // 서버 창(cmd)만 닫으면 그 아래 node/python이 남아 메모리를 계속 잡는다 — 이 창이 종료 스위치다.
            Console.WriteLine("Keep this window open while you use the app.");
            Console.WriteLine("Close this window (or press any key) to stop the backend and frontend and free their memory.");
        }
        else
        {
            Console.WriteLine("Could not tie the servers to this window, so closing it will NOT stop them.");
            Console.WriteLine("Stop them from Task Manager (python.exe / node.exe) when you are done.");
        }
        Pause();
    }

    // 특정 PC의 절대경로를 박지 않는다 — 1) 프로젝트 전용 venv, 2) Windows Python
    // 런처(py), 3) PATH의 python 순으로 이 컴퓨터에 실제로 있는 것만 쓴다.
    static string FindPython(string backendDir)
    {
        string venvPython = Path.Combine(backendDir, ".venv", "Scripts", "python.exe");
        if (File.Exists(venvPython)) return venvPython;
        if (CommandExists("py", "--version")) return "py";
        if (CommandExists("python", "--version")) return "python";
        return null;
    }

    static bool CommandExists(string exe, string args)
    {
        try
        {
            var psi = new ProcessStartInfo(exe, args)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using (var p = Process.Start(psi))
            {
                p.WaitForExit(3000);
                return p.HasExited && p.ExitCode == 0;
            }
        }
        catch (Exception)
        {
            return false;
        }
    }

    static void StartInCmdWindow(string title, string command, string workDir)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = "/k title " + title + " && " + command,
            WorkingDirectory = workDir,
            UseShellExecute = true,
        };
        Process.Start(psi);
    }

    static void Pause()
    {
        Console.WriteLine("Press any key to close this window...");
        Console.ReadKey();
    }
}
