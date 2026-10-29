using System.IO;
using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using ChatArchive;

static class BatchExportChecks
{
    static readonly BindingFlags Flags = BindingFlags.Instance | BindingFlags.NonPublic;
    static T Field<T>(object target, string name) => (T)target.GetType().GetField(name, Flags)!.GetValue(target)!;
    static void Require(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }

    public static async Task<int> Run(Window owner, string? screenshots)
    {
        var workspace = new DirectoryInfo(AppContext.BaseDirectory);
        while (workspace.Parent != null && !File.Exists(Path.Combine(workspace.FullName, "src", "reader.py"))) workspace = workspace.Parent;
        var temporary = Path.Combine(workspace.FullName, "build", "batch-check-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        var preferencesPath = Path.Combine(temporary, "batch-export.json");
        BatchExportWindow? window = null;
        try
        {
            Require(BatchExportPreferences.Load(preferencesPath).Mode == "merged", "Missing preferences did not use defaults");
            File.WriteAllText(preferencesPath, "broken JSON");
            Require(BatchExportPreferences.Load(preferencesPath).Chats.Length == 0, "Broken preferences blocked export");
            new BatchExportPreferences { Chats = ["a", "missing"], Mode = "separate" }.Save(preferencesPath);
            var prefs = BatchExportPreferences.Load(preferencesPath);
            Require(prefs.Chats.SequenceEqual(new[] { "a", "missing" }) && prefs.Mode == "separate", "Preferences did not roundtrip");
            var chats = new[]
            {
                new Chat("a", "宣传部工作群（合成示例）", ""),
                new Chat("b", "新媒体日常工作群（合成示例）", ""),
                new Chat("c", "摄影与视频协作群（合成示例）", ""),
                new Chat("d", "公众号推文审核群（合成示例）", ""),
                new Chat("e", "部门活动统筹群1️⃣2️⃣（合成示例）", ""),
                new Chat("f", new string('长', 80) + "群聊（合成示例）", "")
            };
            window = new BatchExportWindow(chats, prefs, temporary) { Owner = owner, Left = -20000, Top = 0, ShowActivated = false, ShowInTaskbar = false, WindowStartupLocation = WindowStartupLocation.Manual };
            window.Show(); await Idle(window);
            Require(window.SelectedChats.SequenceEqual(new[] { "a" }) && window.Mode == "separate", "Remembered selection includes unavailable groups");
            var list = Field<ListBox>(window, "list");
            var search = Field<TextBox>(window, "search");
            var export = Field<Button>(window, "export");
            // Toggle a real bound checkbox, then change search results twice.
            var secondItem = (ListBoxItem)list.ItemContainerGenerator.ContainerFromIndex(1);
            var check = Descendants(secondItem).OfType<CheckBox>().Single();
            check.IsChecked = true; await Idle(window);
            search.Text = "摄影"; await Idle(window);
            Require(list.Items.Count == 1 && window.SelectedChats.Length == 2, "Search discarded checked groups");
            search.Text = "no-match"; await Idle(window);
            Require(list.Items.Count == 0 && window.SelectedChats.Length == 2 && export.IsEnabled, "Empty search discarded selection");
            search.Text = "";
            var choices = Field<List<BatchChatChoice>>(window, "choices");
            foreach (var choice in choices) choice.IsChecked = false;
            Require(!export.IsEnabled, "Empty group selection can export");
            foreach (var choice in choices.Take(5)) choice.IsChecked = true;
            Field<RadioButton>(window, "merged").IsChecked = true;
            Require(window.Mode == "merged" && Field<RadioButton>(window, "separate").IsChecked == false, "Export modes are not mutually exclusive");
            var start = Field<DatePicker>(window, "start"); var end = Field<DatePicker>(window, "end");
            start.SelectedDate = new DateTime(2026, 10, 17); end.SelectedDate = new DateTime(2026, 10, 16);
            var validate = typeof(BatchExportWindow).GetMethod("CanExport", Flags)!;
            Require(!(bool)validate.Invoke(window, null)!, "Reversed dates accepted");
            end.SelectedDate = null;
            Require(!(bool)validate.Invoke(window, null)!, "Missing date accepted");
            end.SelectedDate = new DateTime(2026, 10, 23);
            Require((bool)validate.Invoke(window, null)!, "Valid settings rejected");
            var folder = Field<TextBox>(window, "folder"); folder.Text = Path.Combine(temporary, "missing");
            Require(!(bool)validate.Invoke(window, null)!, "Missing folder accepted");
            folder.Text = temporary; validate.Invoke(window, null);
            foreach (var size in new[] { new Size(920, 700), new Size(840, 600) })
            {
                window.Width = size.Width; window.Height = size.Height; await Idle(window);
                var content = (FrameworkElement)window.Content;
                var bounds = export.TransformToAncestor(content).TransformBounds(new Rect(new Point(), export.RenderSize));
                Require(bounds.Left >= 0 && bounds.Top >= 0 && bounds.Right <= content.ActualWidth + 1 && bounds.Bottom <= content.ActualHeight + 1, "Export controls clipped at minimum window size");
                if (screenshots != null) Save(window, Path.Combine(screenshots, size.Width == 920 ? "batch-settings.png" : "batch-settings-compact.png"));
            }
            window.Close(); window = null;
            using var result = JsonDocument.Parse(JsonSerializer.Serialize(new
            {
                folder = temporary, count = 42, thumbnailImages = 2, missingImages = 1,
                results = new[] { new { name = chats[0].Name, status = "exported", count = 42, error = "" },
                    new { name = chats[4].Name, status = "empty", count = 0, error = "" },
                    new { name = chats[2].Name, status = "failed", count = 0, error = "合成读取失败" } }
            }));
            var report = new BatchExportResultWindow(result.RootElement) { Owner = owner, Left = -20000, Top = 0, ShowActivated = false, ShowInTaskbar = false, WindowStartupLocation = WindowStartupLocation.Manual };
            try
            {
                report.Show(); await Idle(report);
                var text = Descendants(report).OfType<TextBox>().Single().Text;
                Require(text.Contains("42 条消息") && text.Contains("没有消息") && text.Contains("合成读取失败"), "Partial results did not display each outcome");
                if (screenshots != null) Save(report, Path.Combine(screenshots, "batch-results.png"));
            }
            finally { report.Close(); }
            await CheckProgressProtocol((MainWindow)owner);
            return 4;
        }
        finally
        {
            window?.Close();
            // Delete only the two synthetic files this check created, never recurse.
            File.Delete(preferencesPath); Directory.Delete(temporary);
        }
    }
    static async Task Idle(Window window)
    {
        window.UpdateLayout(); await window.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle);
    }
    static async Task CheckProgressProtocol(MainWindow owner)
    {
        // The actual desktop Request method reads only synthetic worker replies.
        var start = new ProcessStartInfo("python") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true };
        start.ArgumentList.Add("-u"); start.ArgumentList.Add("-c");
        start.ArgumentList.Add("import sys,json\nfor line in sys.stdin:\n print(json.dumps({'event':'progress','data':{'index':1}}),flush=True)\n print(json.dumps({'event':'progress','data':{'index':2}}),flush=True)\n print(json.dumps({'ok':True,'data':{'count':42}}),flush=True)");
        using var worker = Process.Start(start)!;
        var workerField = typeof(MainWindow).GetField("worker", Flags)!;
        workerField.SetValue(owner, worker);
        try
        {
            var progress = new List<int>();
            var method = typeof(MainWindow).GetMethod("Request", Flags)!;
            var first = (Task<JsonElement>)method.Invoke(owner, new object?[] { new { action = "synthetic" }, (Action<JsonElement>)(p => progress.Add(p.GetProperty("index").GetInt32())) })!;
            Require((await first.WaitAsync(TimeSpan.FromSeconds(10))).GetProperty("count").GetInt32() == 42 && progress.SequenceEqual(new[] { 1, 2 }), "Desktop did not consume progress before result");
            var second = (Task<JsonElement>)method.Invoke(owner, new object?[] { new { action = "synthetic" }, null })!;
            Require((await second.WaitAsync(TimeSpan.FromSeconds(10))).GetProperty("count").GetInt32() == 42, "Next desktop request consumed stale progress");
        }
        finally
        {
            workerField.SetValue(owner, null);
            if (!worker.HasExited) worker.Kill(true);
        }
    }
    static IEnumerable<DependencyObject> Descendants(DependencyObject parent)
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            var child = VisualTreeHelper.GetChild(parent, i); yield return child;
            foreach (var nested in Descendants(child)) yield return nested;
        }
    }
    static void Save(Window window, string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var content = (FrameworkElement)window.Content;
        var bitmap = new RenderTargetBitmap((int)Math.Ceiling(content.ActualWidth + 56), (int)Math.Ceiling(content.ActualHeight + 56), 96, 96, PixelFormats.Pbgra32);
        var visual = new DrawingVisual();
        using (var drawing = visual.RenderOpen())
        {
            drawing.DrawRectangle(Brushes.White, null, new Rect(0, 0, bitmap.PixelWidth, bitmap.PixelHeight));
            drawing.DrawRectangle(new VisualBrush(content), null, new Rect(28, 28, content.ActualWidth, content.ActualHeight));
        }
        bitmap.Render(visual); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var output = File.Create(path); encoder.Save(output);
    }
}
