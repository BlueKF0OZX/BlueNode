using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace BlueNode.Setup;

internal sealed class SetupWindow : Form
{
    private readonly TextBox host = new() { PlaceholderText = "Example: 192.168.1.50 or allstar.local" };
    private readonly TextBox user = new() { PlaceholderText = "Your ASL3 Linux username" };
    private readonly TextBox secret = new() { UseSystemPasswordChar = true };
    private readonly TextBox key = new() { PlaceholderText = "Optional: SSH private key file" };
    private readonly TextBox sudo = new() { UseSystemPasswordChar = true, PlaceholderText = "Usually the same as your login password" };
    private readonly NumericUpDown sshPort = new() { Minimum = 1, Maximum = 65535, Value = 22 };
    private readonly NumericUpDown webPort = new() { Minimum = 1024, Maximum = 65535, Value = 8080 };
    private readonly ComboBox nodes = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly TextBox callsign = new() { CharacterCasing = CharacterCasing.Upper, MaxLength = 20 };
    private readonly Button connect = new() { Text = "1. Find my station", AutoSize = true };
    private readonly Button install = new() { Text = "2. Install BlueNode", AutoSize = true, Enabled = false };
    private readonly Button open = new() { Text = "3. Open dashboard", AutoSize = true, Enabled = false };
    private readonly Label status = new() { AutoSize = true, MaximumSize = new Size(700, 0), Text = "Ready when you are. Enter the login you use to manage your AllStar node." };
    private readonly TableLayoutPanel credentials = Grid();
    private readonly TableLayoutPanel station = Grid();
    private readonly TableLayoutPanel advanced = Grid();
    private readonly ProgressBar progress = new() { Dock = DockStyle.Top, Height = 5, Visible = false, Style = ProgressBarStyle.Marquee };
    private readonly CancellationTokenSource closing = new();
    private NodeSession? session;
    private JsonObject? stationInfo;
    private JsonObject? detected;
    private string? dashboardUrl;
    private bool busy;
    private bool installing;
    private readonly string preferences = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BlueNode", "setup.json");
    private SavedSettings saved = new();

    internal sealed class SavedSettings
    {
        public string Host { get; set; } = "";
        public string User { get; set; } = "";
        public int Port { get; set; } = 22;
        public Dictionary<string, string> Keys { get; set; } = new();
    }

    public SetupWindow()
    {
        Text = "BlueNode • Easy setup";
        Font = new Font("Segoe UI", 10);
        BackColor = Color.FromArgb(242, 246, 251);
        ForeColor = Color.FromArgb(25, 43, 65);
        ClientSize = new Size(880, 900); MinimumSize = new Size(700, 660);
        StartPosition = FormStartPosition.CenterScreen;
        var page = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true, Padding = new Padding(28) };
        Controls.Add(page);
        var title = new Label { Text = "Your radio. One simple dashboard.", AutoSize = true, Font = new Font(Font, FontStyle.Bold), Margin = new Padding(0, 0, 0, 12) };
        title.Font = new Font("Segoe UI", 20, FontStyle.Bold); page.Controls.Add(title);
        page.Controls.Add(Note("BlueNode Setup  •  Windows  •  Early-testing alpha", 8));
        page.Controls.Add(Note("Please report any problems during installation, after installation, or while using the dashboard.", 4));
        var reportIssue = new LinkLabel { Text = "Report a problem on GitHub", AutoSize = true, Margin = new Padding(0, 0, 0, 12) };
        reportIssue.LinkClicked += (_, _) => Launch("https://github.com/BlueKF0OZX/BlueNode/issues/new"); page.Controls.Add(reportIssue);
        page.Controls.Add(Note("Start with a working AllStarLink 3 node on Debian 12. This app adds BlueNode to it.\nYour computer and node need to be able to reach each other.", 18));
        AddRow(credentials, "Node address", host);
        AddRow(credentials, "Linux username", user);
        AddRow(credentials, "Login password", secret);
        page.Controls.Add(credentials);
        var more = new LinkLabel { Text = "Advanced: SSH key, ports, or separate sudo password", AutoSize = true, Margin = new Padding(0, 6, 0, 8) };
        more.LinkClicked += (_, _) => advanced.Visible = !advanced.Visible; page.Controls.Add(more);
        AddRow(advanced, "SSH port", sshPort);
        var keyLine = new TableLayoutPanel { AutoSize = true, ColumnCount = 2, Dock = DockStyle.Fill };
        keyLine.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); keyLine.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        var browse = new Button { Text = "Browse…", AutoSize = true };
        browse.Click += (_, _) => { using var dialog = new OpenFileDialog { Title = "Select your SSH private key" }; if (dialog.ShowDialog(this) == DialogResult.OK) key.Text = dialog.FileName; };
        key.Dock = DockStyle.Fill; keyLine.Controls.Add(key); keyLine.Controls.Add(browse);
        AddRow(advanced, "Private key", keyLine); AddRow(advanced, "Sudo password", sudo); AddRow(advanced, "Dashboard port", webPort);
        advanced.Controls.Add(Note("With a key selected, use Login password for its passphrase (if it has one).", 4), 0, advanced.RowCount++);
        advanced.SetColumnSpan(advanced.Controls[^1], 2); advanced.Visible = false; page.Controls.Add(advanced);
        page.Controls.Add(connect);
        page.Controls.Add(Note("Your station", 10));
        AddRow(station, "Local node", nodes); AddRow(station, "Callsign", callsign); station.Enabled = false; page.Controls.Add(station);
        page.Controls.Add(Note("Private access is automatic. Keep this app open while using your dashboard.\nNo router changes. No settings files to edit. Automatic radio recovery stays off.", 14));
        var actions = new FlowLayoutPanel { AutoSize = true, WrapContents = false, Margin = new Padding(0, 0, 0, 12) };
        actions.Controls.Add(install); actions.Controls.Add(open); page.Controls.Add(actions);
        page.Controls.Add(progress); page.Controls.Add(status);
        var help = new LinkLabel { Text = "Setup help / I don't know my node login", AutoSize = true, Margin = new Padding(0, 16, 0, 8) };
        help.LinkClicked += (_, _) => Launch("https://github.com/BlueKF0OZX/BlueNode/blob/main/docs/WINDOWS_SETUP.md"); page.Controls.Add(help);
        var licenses = new LinkLabel { Text = "Open-source licenses", AutoSize = true };
        licenses.LinkClicked += (_, _) =>
        {
            var assembly = System.Reflection.Assembly.GetExecutingAssembly();
            var text = new System.Text.StringBuilder();
            foreach (var name in assembly.GetManifestResourceNames().Where(n => n.EndsWith(".txt")))
            {
                using var reader = new StreamReader(assembly.GetManifestResourceStream(name)!);
                text.AppendLine(name).AppendLine(reader.ReadToEnd()).AppendLine();
            }
            using var dialog = new Form { Text = "BlueNode and third-party licenses", Size = new Size(780, 600), StartPosition = FormStartPosition.CenterParent };
            dialog.Controls.Add(new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, Dock = DockStyle.Fill, Text = text.ToString() });
            dialog.ShowDialog(this);
        };
        page.Controls.Add(licenses);
        page.SizeChanged += (_, _) => { var width = Math.Max(560, page.ClientSize.Width - 75); credentials.MinimumSize = station.MinimumSize = advanced.MinimumSize = new Size(width, 0); progress.Width = width; status.MaximumSize = new Size(width, 0); title.MaximumSize = new Size(width, 0); };
        nodes.SelectedIndexChanged += (_, _) => { if (detected != null && nodes.SelectedItem is string number) callsign.Text = detected[number]?.GetValue<string>() ?? ""; };
        connect.Click += async (_, _) => await Run(Connect);
        install.Click += async (_, _) => await Run(Install);
        open.Click += async (_, _) => await Run(OpenDashboard);
        try { if (File.Exists(preferences)) saved = JsonSerializer.Deserialize<SavedSettings>(File.ReadAllText(preferences)) ?? new(); } catch { }
        host.Text = saved.Host; user.Text = saved.User; sshPort.Value = Math.Clamp(saved.Port, 1, 65535);
        void Changed(object? sender, EventArgs e)
        {
            if (busy) return;
            stationInfo = detected = null; install.Enabled = open.Enabled = false; station.Enabled = false;
            status.Text = "Click Find my station to check these connection details.";
        }
        foreach (var field in new[] { host, user, secret, key, sudo }) field.TextChanged += Changed;
        sshPort.ValueChanged += Changed;
        FormClosing += (_, e) =>
        {
            if (busy && !installing) { e.Cancel = true; status.Text = "Please let the current connection check finish before closing."; return; }
            if (installing && MessageBox.Show(this, "Setup will continue safely on your node. Reopen this app and connect to check the result. Close now?", "Setup is running", MessageBoxButtons.YesNo) != DialogResult.Yes) { e.Cancel = true; return; }
            closing.Cancel();
            // Avoid synchronous network cleanup on the UI thread during shutdown.
            // Random temporary uploads are documented; normal reconnect disposes them.
        };
        FormClosed += (_, _) => { _ = Task.Run(() => session?.Dispose()); };
    }

    private static TableLayoutPanel Grid()
    {
        var grid = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, MinimumSize = new Size(730, 0), Margin = new Padding(0, 0, 0, 8) };
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 180)); grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); return grid;
    }
    private static void AddRow(TableLayoutPanel table, string text, Control control)
    {
        var row = table.RowCount++; table.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        table.Controls.Add(new Label { Text = text, AutoSize = true, Margin = new Padding(0, 8, 8, 6) }, 0, row);
        control.Dock = DockStyle.Fill; control.Margin = new Padding(0, 3, 0, 7); table.Controls.Add(control, 1, row);
    }
    private static Label Note(string text, int below) => new() { Text = text, AutoSize = true, MaximumSize = new Size(730, 0), Margin = new Padding(0, 0, 0, below) };
    private static void Launch(string url) => Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });

    private void Save()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(preferences)!);
        File.WriteAllText(preferences, JsonSerializer.Serialize(saved));
    }
    private bool Trust(string name, string fingerprint)
    {
        if (InvokeRequired) return (bool)Invoke(() => Trust(name, fingerprint));
        if (saved.Keys.TryGetValue(name, out var known))
        {
            if (known == fingerprint) return true;
            MessageBox.Show(this, "This node's SSH identity has changed. Connection blocked. Check that you have the right node; see Setup help if you intentionally rebuilt it.", "Identity changed", MessageBoxButtons.OK, MessageBoxIcon.Warning); return false;
        }
        if (MessageBox.Show(this, $"First connection to {name}.\n\nSSH identity:\n{fingerprint}\n\nConfirm this is your node. If someone manages it for you, ask them to verify this fingerprint. Save this identity and continue?", "Recognize your node", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return false;
        saved.Keys[name] = fingerprint; Save(); return true;
    }

    private async Task Run(Func<Task> work)
    {
        if (busy) return;
        busy = true; connect.Enabled = install.Enabled = open.Enabled = false;
        credentials.Enabled = advanced.Enabled = station.Enabled = false; progress.Visible = true;
        try { await work(); }
        catch (OperationCanceledException) { }
        catch (Renci.SshNet.Common.SshAuthenticationException) { status.Text = "Login wasn't accepted. Use your node's Linux username/password, not your callsign or AllStar website password."; }
        catch (Renci.SshNet.Common.SshConnectionException) { status.Text = "The SSH connection closed or its identity wasn't accepted. Check the node address and reconnect."; }
        catch (System.Net.Sockets.SocketException) { status.Text = "Couldn't reach the node. Check its address, SSH port, and that it is switched on and reachable from this computer."; }
        catch (Exception error) { status.Text = "Setup stopped: " + error.Message; }
        finally
        {
            if (!IsDisposed)
            {
                busy = installing = false; progress.Visible = false; connect.Enabled = true;
                credentials.Enabled = advanced.Enabled = true; station.Enabled = detected != null;
                install.Enabled = detected != null && stationInfo == null; open.Enabled = stationInfo != null;
            }
        }
    }

    private async Task Connect()
    {
        status.Text = "Connecting and checking your AllStar station…";
        stationInfo = detected = null; dashboardUrl = null; nodes.Items.Clear();
        var old = session; session = null; if (old != null) await Task.Run(old.Dispose);
        var candidate = new NodeSession(host.Text, (int)sshPort.Value, user.Text, secret.Text, key.Text.Trim(), sudo.Text, Trust);
        try { await Task.Run(candidate.Connect); session = candidate; }
        catch { await Task.Run(candidate.Dispose); throw; }
        saved.Host = host.Text.Trim(); saved.User = user.Text.Trim(); saved.Port = (int)sshPort.Value; Save();
        secret.Clear(); sudo.Clear();
        var result = await session.Request(new { action = "probe" });
        if (result["mode"]!.GetValue<string>() == "running") { await Follow(result["job"]!.GetValue<string>()); return; }
        if (result["mode"]!.GetValue<string>() == "existing") { Ready((JsonObject)result["station"]!); return; }
        detected = (JsonObject)result["nodes"]!;
        foreach (var entry in detected) nodes.Items.Add(entry.Key);
        if (nodes.Items.Count == 1) nodes.SelectedIndex = 0;
        status.Text = "Station found. Confirm your local node and callsign, then click Install BlueNode.";
        if (result["previous"] is JsonObject previous && previous["state"]?.GetValue<string>() == "failed")
            status.Text += "\nThe previous attempt failed: " + previous["message"]?.GetValue<string>() + "\nPrivate node log: " + previous["log"]?.GetValue<string>();
    }

    private async Task Install()
    {
        if (session == null || nodes.SelectedItem is not string number || string.IsNullOrWhiteSpace(callsign.Text))
            throw new InvalidOperationException("Choose your local node and enter your callsign first.");
        if (MessageBox.Show(this, $"Install BlueNode for {callsign.Text}, node {number}?\n\nIt will start automatically on the node. Access will be private through this app. Your Asterisk settings stay as they are.\n\nThis is an early-testing alpha release.", "Ready to install", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        status.Text = "Starting installation…";
        var result = await session.Request(new { action = "start", node = number, callsign = callsign.Text, port = (int)webPort.Value, confirmed = true });
        await Follow(result["job"]!.GetValue<string>());
    }

    private async Task Follow(string job)
    {
        installing = true;
        while (!closing.IsCancellationRequested)
        {
            status.Text = "Installing and checking BlueNode… This usually takes a minute. Your radio keeps running.\nIf this connection closes, reconnect to check the result.";
            var result = await session!.Request(new { action = "status", job });
            var state = result["state"]!.GetValue<string>();
            if (state == "complete") { Ready((JsonObject)result["station"]!); return; }
            if (state == "failed") throw new InvalidOperationException(result["message"]!.GetValue<string>() + "\nPrivate node log: " + result["log"]!.GetValue<string>());
            await Task.Delay(1500, closing.Token);
        }
    }
    private void Ready(JsonObject value)
    {
        stationInfo = (JsonObject)value.DeepClone(); detected = null;
        nodes.Items.Clear(); nodes.Items.Add(value["node"]!.GetValue<string>()); nodes.SelectedIndex = 0;
        callsign.Text = value["callsign"]!.GetValue<string>();
        status.Text = "BlueNode is ready. Click Open dashboard.\nKeep this app open while you use it; your node keeps running when you close it.";
    }
    private async Task OpenDashboard()
    {
        if (stationInfo == null || session == null) return;
        dashboardUrl = await Task.Run(() => session.OpenTunnel(stationInfo));
        using var client = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(15) };
        var response = await client.GetStringAsync(dashboardUrl);
        if (!response.Contains("BlueNode", StringComparison.Ordinal)) throw new InvalidOperationException("The dashboard did not pass its connection check. Reconnect and try again.");
        Launch(dashboardUrl);
        status.Text = "Dashboard opened. Keep this app open for the private connection.\nNext time: open BlueNode Setup, sign in, and click Open dashboard.";
    }
}
