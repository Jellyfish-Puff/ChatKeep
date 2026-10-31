using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using System.Windows.Input;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;
using ChatArchive;

static class ToolbarChecks
{
    const BindingFlags Flags = BindingFlags.Instance | BindingFlags.NonPublic;
    static void Require(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    static async Task Settle(Window window)
    {
        window.UpdateLayout(); await window.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle); window.UpdateLayout();
    }
    static void Call(MainWindow window, string name, params object?[] args) => typeof(MainWindow).GetMethod(name, Flags)!.Invoke(window, args);
    static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var child = VisualTreeHelper.GetChild(root, i); yield return child;
            foreach (var nested in Descendants(child)) yield return nested;
        }
    }
    public static async Task<int> Run(MainWindow window, string? screenshots)
    {
        var fixtures = new[]
        {
            new { id = "synthetic:1", time = 1793271600, sender = "合成示例", self = false, text = "摄影活动的宣传安排，请周五前完成。", image = (string?)null },
            new { id = "synthetic:2", time = 1793358000, sender = "我", self = true, text = "收到，我来整理配图。", image = (string?)null },
            new { id = "synthetic:3", time = 1793530800, sender = "合成示例", self = false, text = "摄影征稿推文已更新。", image = (string?)null }
        };
        var processStart = new ProcessStartInfo("python") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true };
        processStart.Environment["PYTHONIOENCODING"] = "utf-8";
        processStart.ArgumentList.Add("-u"); processStart.ArgumentList.Add("-c");
        processStart.ArgumentList.Add("import json,sys\nnormal=json.loads(sys.argv[1]); matches=json.loads(sys.argv[2])\nfor line in sys.stdin:\n r=json.loads(line.lstrip('\\ufeff'))\n data=([] if r.get('before') is not None else matches) if r['action']=='search' else normal\n print(json.dumps({'ok':True,'data':data}),flush=True)");
        processStart.ArgumentList.Add(JsonSerializer.Serialize(fixtures.Take(2)));
        processStart.ArgumentList.Add(JsonSerializer.Serialize(fixtures.Skip(2)));
        using var worker = Process.Start(processStart)!;
        var workerField = typeof(MainWindow).GetField("worker", Flags)!; workerField.SetValue(window, worker);
        var busyField = typeof(MainWindow).GetField("busy", Flags)!;
        var chatField = typeof(MainWindow).GetField("chat", Flags)!;
        var messages = (List<JsonElement>)typeof(MainWindow).GetField("messages", Flags)!.GetValue(window)!;
        var chats = (List<Chat>)typeof(MainWindow).GetField("chats", Flags)!.GetValue(window)!;
        var toggle = (ToggleButton)window.FindName("SelectionMode");
        var export = (Button)window.FindName("ExportButton");
        var search = (TextBox)window.FindName("MessageSearch");
        var toolbar = (Grid)window.FindName("MessageToolbar");
        var count = (TextBlock)window.FindName("SelectionCount");
        var panel = (StackPanel)window.FindName("MessagePanel");
        try
        {
            busyField.SetValue(window, true); Call(window, "ResetConversationTools");
            chatField.SetValue(window, "synthetic@chatroom");
            chats.Clear();
            for (var i = 0; i < 15; i++) chats.Add(new("synthetic-" + i, "宣传部工作群（合成示例）" + (i + 1), "工作安排已更新。"));
            Call(window, "ApplySearch"); ((ListBox)window.FindName("ChatList")).SelectedIndex = 1;
            ((TextBlock)window.FindName("ChatTitle")).Text = "宣传部工作群（群名称很长时会省略，完整名称可悬停查看 · 合成示例）";
            ((TextBlock)window.FindName("Status")).Text = "界面预览 · 合成示例";
            ((TextBlock)window.FindName("GroupCount")).Text = "15 个群聊 · 合成示例";
            var load = typeof(MainWindow).GetMethod("LoadMessages", Flags)!;
            await ((Task)load.Invoke(window, new object?[] { false, null, true })!).WaitAsync(TimeSpan.FromSeconds(10));
            Require(export.IsEnabled && toggle.Content.Equals("选择"), "Normal date export should remain available");
            Require(export.Content.Equals("导出"), "Toolbar should use the general export label");
            Require(!ClickRow(Descendants(panel).OfType<TextBox>().First()), "Normal browsing should preserve text mouse selection");
            foreach (var width in new[] { 1380d, 1100d, 960d })
            {
                window.Width = width; window.Height = width == 1380 ? 900 : 640; await Settle(window);
                var title = (TextBlock)window.FindName("ChatTitle");
                Require(window.MinWidth == 960 && window.MinHeight == 640, "Window minimum must be 960 by 640");
                var titleBounds = title.TransformToAncestor(window).TransformBounds(new Rect(new Point(), title.RenderSize));
                var toolsBounds = toolbar.TransformToAncestor(window).TransformBounds(new Rect(new Point(), toolbar.RenderSize));
                Require(titleBounds.Right < toolsBounds.Left, "Long group name overlaps toolbar");
                Require(title.ActualWidth >= 80, "Group title has no readable space at minimum width");
                Require(toolsBounds.Right < window.ActualWidth && toolsBounds.Height <= 40, "Toolbar wraps or clips");
                Require(search.ActualWidth >= 191 && toggle.ActualWidth == 72 && export.ActualWidth == toggle.ActualWidth, "Search is too narrow or selection/export buttons have different widths");
                var childBounds = toolbar.Children.OfType<FrameworkElement>().Select(control => control.TransformToAncestor(window).TransformBounds(new Rect(new Point(), control.RenderSize))).ToArray();
                for (var i = 1; i < childBounds.Length; i++)
                    Require(childBounds[i - 1].Right <= childBounds[i].Left && Math.Abs(childBounds[i].Top - childBounds[0].Top) < 1, "Toolbar controls overlap or leave single row");
                foreach (var button in toolbar.Children.OfType<FrameworkElement>())
                    Require(button.ActualWidth > 0 && button.ActualHeight <= 40, "Toolbar control is hidden or wraps");
                if (screenshots != null) Save(window, Path.Combine(screenshots, width == 1380 ? "message-toolbar.png" : width == 960 ? "message-toolbar-minimum.png" : "message-toolbar-medium.png"));
            }
            toggle.IsChecked = true; toggle.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
            Require(!export.IsEnabled && toggle.Content.Equals("选择中"), "Selection mode should show a plain label and disable empty export");
            var firstRow = (Grid)panel.Children[0];
            var firstCheck = Descendants(firstRow).OfType<CheckBox>().Single();
            var firstText = Descendants(firstRow).OfType<TextBox>().Single();
            var firstBubble = (Border)((StackPanel)firstRow.Children[1]).Children[1];
            Require(ClickRow(firstText) && firstCheck.IsChecked == true, "Clicking message text should select the row");
            Require(((SolidColorBrush)firstBubble.BorderBrush).Color.A == 255 && firstBubble.BorderThickness.Left == 2, "Selected bubble has no visible border");
            Require(ClickRow(firstRow) && firstCheck.IsChecked == false && ((SolidColorBrush)firstBubble.BorderBrush).Color.A == 0, "Clicking row whitespace should deselect and clear border");
            Require(!ClickRow(firstCheck), "Row handler consumes native checkbox click");
            ((IToggleProvider)new ToggleButtonAutomationPeer(firstCheck).GetPattern(PatternInterface.Toggle)).Toggle();
            Require(export.IsEnabled && count.Text.Contains("1") && toggle.Content.Equals("选择中"), "Checking a message did not update footer count or kept count in button");
            search.Text = "摄影";
            await ((Task)load.Invoke(window, new object?[] { false, "摄影", true })!).WaitAsync(TimeSpan.FromSeconds(10));
            Require(messages.Single().GetProperty("id").GetString() == "synthetic:3", "Search did not display reader results");
            Require(count.Text.Contains("1") && toggle.Content.Equals("选择中"), "Search discarded a hidden checked message");
            Descendants(panel).OfType<CheckBox>().Single().IsChecked = true;
            var settings = (ExportWindow)typeof(MainWindow).GetMethod("CreateExportDialog", Flags)!.Invoke(window, null)!;
            Require(settings.OnlySelected, "Export dialog should default to checked messages");
            using var request = JsonDocument.Parse(JsonSerializer.Serialize(typeof(MainWindow).GetMethod("ExportRequest", Flags)!.Invoke(window, new object[] { settings, "synthetic.html" })));
            var ids = request.RootElement.GetProperty("selected").EnumerateArray().Select(x => x.GetString()).ToHashSet();
            Require(ids.SetEquals(new[] { "synthetic:1", "synthetic:3" }), "Direct export lost selections outside search view");
            var expectedFirst = DateTimeOffset.FromUnixTimeSeconds(fixtures[0].time).LocalDateTime.ToString("yyyy-MM-dd");
            var expectedLast = DateTimeOffset.FromUnixTimeSeconds(fixtures[2].time).LocalDateTime.ToString("yyyy-MM-dd");
            Require(request.RootElement.GetProperty("start").GetString() == expectedFirst && request.RootElement.GetProperty("end").GetString() == expectedLast, "Direct export does not cover all selected dates");
            Require(!request.RootElement.TryGetProperty("query", out _), "Direct export mistakenly reapplies visible search filter");
            ((DatePicker)settings.FindName("StartPicker")).SelectedDate=new DateTime(2026,10,30);
            ((DatePicker)settings.FindName("EndPicker")).SelectedDate=new DateTime(2026,10,30);
            using var changedDates = JsonDocument.Parse(JsonSerializer.Serialize(typeof(MainWindow).GetMethod("ExportRequest", Flags)!.Invoke(window, new object[] { settings, "synthetic.html" })));
            Require(changedDates.RootElement.GetProperty("start").GetString()=="2026-10-30" && changedDates.RootElement.GetProperty("end").GetString()=="2026-10-30", "Export request ignores edited dialog dates");
            ((ComboBox)settings.FindName("ContentPicker")).SelectedIndex = 0;
            using var allRequest = JsonDocument.Parse(JsonSerializer.Serialize(typeof(MainWindow).GetMethod("ExportRequest", Flags)!.Invoke(window, new object[] { settings, "synthetic.html" })));
            Require(allRequest.RootElement.GetProperty("selected").ValueKind == JsonValueKind.Null, "All-record export still filters by selected IDs");
            settings.Close();
            Require(count.Text.Contains("2") && toggle.Content.Equals("选择中"), "Selection count must stay in footer only");
            window.Width = 960; window.Height = 640; await Settle(window);
            if (screenshots != null) Save(window, Path.Combine(screenshots, "message-toolbar-selecting.png"));
            // Clear via the real control event, then wait for its asynchronous normal reload.
            search.Clear();
            for (var i = 0; i < 100 && (bool)busyField.GetValue(window)!; i++) await Task.Delay(20);
            Require(!(bool)busyField.GetValue(window)! && messages.Count == 2, "Clearing search did not restore normal messages");
            Require(count.Text.Contains("2") && toggle.Content.Equals("选择中"), "Clearing search discarded selected messages");
            toggle.IsChecked = false; toggle.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
            Require(toggle.Content.Equals("选择") && export.IsEnabled && Descendants(panel).OfType<CheckBox>().All(c => c.Visibility == Visibility.Collapsed), "Exiting selection did not restore normal mode");
            var selected = (HashSet<string>)typeof(MainWindow).GetField("selected", Flags)!.GetValue(window)!;
            Require(selected.Count == 0, "Exiting selection left hidden checked messages");
            search.Text = "摄影"; Call(window, "ResetConversationTools");
            Require(search.Text == "" && toggle.IsChecked != true, "Switching conversations keeps stale tools");
            return 3;
        }
        finally
        {
            workerField.SetValue(window, null);
            if (!worker.HasExited) worker.Kill(true);
            busyField.SetValue(window, true); Call(window, "ResetConversationTools");
            messages.Clear(); panel.Children.Clear(); chats.Clear(); chatField.SetValue(window, null);
            busyField.SetValue(window, false);
        }
    }
    static bool ClickRow(UIElement source)
    {
        var e = new MouseButtonEventArgs(Mouse.PrimaryDevice, Environment.TickCount, MouseButton.Left) { RoutedEvent = Mouse.PreviewMouseDownEvent };
        source.RaiseEvent(e); return e.Handled;
    }
    static void Save(Window window, string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var content = (FrameworkElement)window.Content;
        var bitmap = new RenderTargetBitmap((int)Math.Ceiling(content.ActualWidth), (int)Math.Ceiling(content.ActualHeight), 96, 96, PixelFormats.Pbgra32);
        var visual = new DrawingVisual();
        using (var drawing = visual.RenderOpen()) drawing.DrawRectangle(new VisualBrush(content), null, new Rect(0, 0, bitmap.PixelWidth, bitmap.PixelHeight));
        bitmap.Render(visual); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var output = File.Create(path); encoder.Save(output);
    }
}
