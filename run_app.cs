using System;
using System.Diagnostics;
using System.IO;

class Launcher
{
    // ponytail: 이 컴퓨터의 실제 경로를 그대로 박음 — 다른 PC로 옮기면 이 줄만 고치면 됨.
    const string PythonExe = @"C:\Users\재혁\AppData\Local\Programs\Python\Python311\python.exe";

    static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string backendDir = Path.Combine(root, "backend");
        string frontendDir = Path.Combine(root, "frontend");

        if (!File.Exists(PythonExe))
        {
            Console.WriteLine("Python not found: " + PythonExe);
            Console.WriteLine("Edit PythonExe in run_app.cs and recompile, or reinstall Python at that path.");
            Pause();
            return;
        }
        if (!Directory.Exists(backendDir) || !Directory.Exists(frontendDir))
        {
            Console.WriteLine("backend/ or frontend/ folder not found next to this exe.");
            Console.WriteLine("Put this exe in the project root (same folder as backend/ and frontend/).");
            Pause();
            return;
        }

        StartInCmdWindow("Backend (uvicorn :8000)",
            "\"" + PythonExe + "\" -m uvicorn app.main:app --host 127.0.0.1 --port 8000", backendDir);

        StartInCmdWindow("Frontend (next dev :3000)", "npm run dev", frontendDir);

        Console.WriteLine("Started backend and frontend in separate windows.");
        Console.WriteLine("Opening the browser in a few seconds...");
        System.Threading.Thread.Sleep(4000);
        Process.Start(new ProcessStartInfo("http://localhost:3000") { UseShellExecute = true });

        Console.WriteLine("This window can be closed. To stop the servers, close the Backend/Frontend windows.");
        Pause();
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
