using System;
using System.Diagnostics;
using System.IO;

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

        StartInCmdWindow("Backend (uvicorn :8000)",
            "\"" + python + "\" -m uvicorn app.main:app --host 127.0.0.1 --port 8000", backendDir);

        StartInCmdWindow("Frontend (next dev :3000)", "npm run dev", frontendDir);

        Console.WriteLine("Started backend and frontend in separate windows.");
        Console.WriteLine("Opening the browser in a few seconds...");
        System.Threading.Thread.Sleep(4000);
        Process.Start(new ProcessStartInfo("http://localhost:3000") { UseShellExecute = true });

        Console.WriteLine("This window can be closed. To stop the servers, close the Backend/Frontend windows.");
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
