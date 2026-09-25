using System.Text.Json.Nodes;
using BlueNode.Setup;

internal static class Checks
{
    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            if (args.Length == 2 && args[0] == "--render")
            {
                ApplicationConfiguration.Initialize();
                using var form = new SetupWindow();
                form.ShowInTaskbar = false; form.Opacity = 0;
                form.Show(); form.PerformLayout(); Application.DoEvents();
                using var bitmap = new Bitmap(form.Width, form.Height);
                form.DrawToBitmap(bitmap, new Rectangle(0, 0, form.Width, form.Height));
                bitmap.Save(Path.GetFullPath(args[1]));
                Console.WriteLine("Rendered setup window"); return 0;
            }
            Run(args).GetAwaiter().GetResult(); return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
    static async Task Run(string[] args)
    {
        string Required(string name) => Environment.GetEnvironmentVariable(name) ?? throw new Exception("Missing " + name);
        var host = Required("BLUENODE_TEST_HOST"); var port = int.Parse(Required("BLUENODE_TEST_PORT"));
        var user = Required("BLUENODE_TEST_USER"); var key = Environment.GetEnvironmentVariable("BLUENODE_TEST_KEY") ?? "";
        var secret = Environment.GetEnvironmentVariable("BLUENODE_TEST_SECRET") ?? "";
        var expected = Required("BLUENODE_TEST_FINGERPRINT");
        NodeSession New(Func<string, string, bool>? trust = null) => new(host, port, user, secret, key, "", trust ?? ((_, fingerprint) => fingerprint == expected));
        if (key.Length == 0)
        {
            using var wrong = new NodeSession(host, port, user, "intentionally-wrong", "", "", (_, fingerprint) => fingerprint == expected);
            try { wrong.Connect(); throw new Exception("Wrong password accepted"); }
            catch (Renci.SshNet.Common.SshAuthenticationException) { Console.WriteLine("PASS rejected wrong password"); }
        }
        using (var rejected = New((_, _) => false))
        {
            try { rejected.Connect(); throw new Exception("Untrusted host was accepted"); }
            catch (Renci.SshNet.Common.SshConnectionException) { Console.WriteLine("PASS rejected untrusted host"); }
        }
        string? job = null;
        using (var initial = New())
        {
            initial.Connect();
            var probe = await initial.Request(new { action = "probe" });
            Console.WriteLine("Probe: " + probe.ToJsonString());
            if (args.Contains("--install"))
            {
                if (probe["mode"]!.GetValue<string>() != "new") throw new Exception("Expected disposable fresh node");
                var result = await initial.Request(new { action = "start", confirmed = true, node = Required("BLUENODE_TEST_NODE"), callsign = "W1AW", port = 8080 });
                job = result["job"]!.GetValue<string>();
            }
            else if (probe["mode"]!.GetValue<string>() == "existing") await Dashboard(initial, (JsonObject)probe["station"]!);
        }
        if (job != null)
        {
            Console.WriteLine("Disconnected deliberately after start; reconnecting");
            using var resumed = New(); resumed.Connect();
            for (var attempt = 0; attempt < 120; attempt++)
            {
                var result = await resumed.Request(new { action = "status", job });
                var state = result["state"]!.GetValue<string>();
                if (state == "failed") throw new Exception(result.ToJsonString());
                if (state == "complete") { await Dashboard(resumed, (JsonObject)result["station"]!); Console.WriteLine("PASS detached installation and reconnect"); return; }
                await Task.Delay(1000);
            }
            throw new Exception("Installation did not finish in time");
        }
    }
    static async Task Dashboard(NodeSession session, JsonObject station)
    {
        var url = session.OpenTunnel(station);
        using var client = new HttpClient(new HttpClientHandler { UseProxy = false });
        var body = await client.GetStringAsync(url);
        if (!body.Contains("BlueNode")) throw new Exception("Wrong dashboard content");
        var state = JsonNode.Parse(await client.GetStringAsync(new Uri(new Uri(url), "/state/system.json")))!;
        if (state["node"]!.ToString() != station["node"]!.ToString()) throw new Exception("Wrong node");
        Console.WriteLine("PASS private tunnel and live station identity");
    }
}
