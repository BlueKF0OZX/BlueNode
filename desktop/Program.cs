namespace BlueNode.Setup;

internal static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        if (args.SequenceEqual(new[] { "--check-package" }))
        {
            using var stream = System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("BlueNode.Payload");
            if (stream == null) return 1;
            using var archive = new System.IO.Compression.ZipArchive(stream);
            foreach (var path in new[] { "install/desktop_bridge.py", "install/quickstart.py", "install/install.sh", "web/welcome.html", "core/version.py", "config/nodesmart.example.json" })
                if (archive.GetEntry(path) == null) return 2;
            return 0;
        }
        Application.Run(new SetupWindow());
        return 0;
    }
}
